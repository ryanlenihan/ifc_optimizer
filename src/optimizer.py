"""Routines for optimizing IFC files.

This module contains a collection of utilities used by both the GUI and a
command line interface to reduce the size of IFC models.  Functions are kept
independent so they can easily be reused or tested in isolation.
"""

from __future__ import annotations

import gzip
import os
import re
import shutil
import time
import traceback

import ifcopenshell
import ifcpatch
from ifcopenshell.util import shape
from ifcopenshell.util.element import replace_attribute


# ----------------------------------------------------------------------
# Text level helpers
# ----------------------------------------------------------------------

_CARTESIAN_POINT_RE = re.compile(r"(IFCCARTESIANPOINT)\(\s*([^)]+)\)")

def apply_lossy_rounding(raw: str, precision: int) -> str:
    """Round coordinates of all ``IfcCartesianPoint`` occurrences.

    Parameters
    ----------
    raw:
        Text content of an IFC file.
    precision:
        Number of decimal places to keep.

    Returns
    -------
    str
        The IFC text with rounded coordinates.
    """

    def _round(match: re.Match) -> str:
        coords = [c.strip() for c in match.group(2).split(",")]
        rounded = []
        for c in coords:
            try:
                rounded.append(str(round(float(c), precision)))
            except ValueError:
                rounded.append(c)
        return f"{match.group(1)}({','.join(rounded)})"

    return _CARTESIAN_POINT_RE.sub(_round, raw)

def merge_cartesian_points(model) -> int:
    """Merge identical ``IfcCartesianPoint`` entities within *model*.

    Returns the number of points removed.
    """

    seen: dict[tuple[float, ...], any] = {}
    dupes = []

    for pt in list(model.by_type("IfcCartesianPoint")):
        key = tuple(float(c) for c in pt.Coordinates)
        if key in seen:
            canon = seen[key]
            for inv in model.get_inverse(pt):
                replace_attribute(inv, pt, canon)
            dupes.append(pt)
        else:
            seen[key] = pt

    for pt in dupes:
        model.remove(pt)

    return len(dupes)

def model_level_dedupe(model, entity_type: str) -> int:
    """Merge duplicate instances of ``entity_type`` within *model*."""

    seen: dict[tuple, any] = {}
    dupes = []

    for inst in list(model.by_type(entity_type)):
        info = inst.get_info(include_identifier=False, recursive=False)
        key = (inst.is_a(),) + tuple(info.values())
        if key in seen:
            canon = seen[key]
            for inv in model.get_inverse(inst):
                replace_attribute(inv, inst, canon)
            dupes.append(inst)
        else:
            seen[key] = inst

    for inst in dupes:
        model.remove(inst)

    return len(dupes)

def write_ifczip(src_ifc: str, dst_ifczip: str) -> None:
    """Write ``src_ifc`` into a gzipped ``.ifczip`` container."""

    with open(src_ifc, "rb") as fin, gzip.open(dst_ifczip, "wb") as fout:
        shutil.copyfileobj(fin, fout)

# -----------------------------------------------------------------------

def optimize_ifc(input_path: str, output_path: str, options: dict | None = None) -> dict:
    """Optimize an IFC file according to *options*.

    Parameters
    ----------
    input_path:
        Path to the source IFC file.
    output_path:
        Path where the optimized file will be written.
    options:
        Dictionary of boolean flags/values controlling which optimisations to
        apply.

    Returns
    -------
    dict
        A dictionary with statistics about the performed operations.
    """

    if options is None:
        options = {}

    start = time.time()
    print("Loading:", input_path)
    tmp_files: list[str] = []

    try:
        # 1. Optional schema conversion ---------------------------------
        if options.get("convert_schema"):
            tmp_schema = input_path + ".conv.ifc"
            convert_schema(input_path, tmp_schema, options["target_schema"])
            tmp_files.append(tmp_schema)
            input_path = tmp_schema

        # 2. Optional lossy coordinate rounding -------------------------
        if "lossy_rounding" in options:
            prec = int(options["lossy_rounding"])
            with open(input_path, "r", encoding="utf-8") as f:
                raw = f.read()
            tmp_round = input_path + ".round.ifc"
            with open(tmp_round, "w", encoding="utf-8") as f:
                f.write(apply_lossy_rounding(raw, prec))
            tmp_files.append(tmp_round)
            input_path = tmp_round

        # 3. Load model -------------------------------------------------
        model = ifcopenshell.open(input_path)
        initial_size = os.path.getsize(input_path) / (1024 * 1024)
        stats: dict[str, int] = {}

        # 4. Model-level optimisations ---------------------------------
        if options.get("merge_cartesian"):
            stats["merged_points"] = merge_cartesian_points(model)
        if options.get("dedupe_property_sets"):
            stats["dup_psets"] = model_level_dedupe(model, "IfcPropertySet")
        if options.get("dedupe_classifications"):
            stats["dup_class"] = model_level_dedupe(model, "IfcClassificationReference")
        if options.get("remove_dash_props"):
            stats["dash_props"] = remove_placeholder_properties(model, "-")

        if options.get("remove_unused_spaces"):
            stats["spaces"] = remove_unused_spaces(model)
        if options.get("remove_metadata"):
            stats["metadata"] = remove_metadata(model)
        if options.get("remove_empty_attributes"):
            stats["empty_attrs"] = remove_empty_attributes(model)
        if options.get("remove_unused_property_sets"):
            stats["psets_unused"] = remove_unused_property_sets(model)
        if options.get("remove_unused_materials"):
            stats["materials_unused"] = remove_unused_materials(model)
        if options.get("remove_unused_classifications"):
            stats["class_unused"] = remove_unused_classifications(model)
        if "remove_small_elements" in options:
            stats["small_elems"] = remove_small_elements(model, options["remove_small_elements"])
        if options.get("remove_orphaned_entities"):
            stats["orphans"] = remove_orphaned_entities(model)
        if options.get("deduplicate_geometry"):
            stats["dup_geo"] = deduplicate_geometry(model)
        if options.get("flatten_spatial_structure"):
            stats["spatial"] = flatten_spatial_structure(model)

        # 5. Write results ----------------------------------------------
        model.write(output_path)
        if options.get("ifczip_compress"):
            write_ifczip(output_path, output_path + ".ifczip")

        # 6. Housekeeping ----------------------------------------------
        for f in tmp_files:
            os.remove(f)

        final_size = os.path.getsize(output_path) / (1024 * 1024)
        print(f"Optimised → {output_path}  ({initial_size:.2f} MB → {final_size:.2f} MB)")
        print("Stats:", stats)
        print("Time  :", f"{time.time() - start:.1f}s")

        return stats

    except Exception as e:  # pragma: no cover - runtime aid
        traceback.print_exc()
        raise RuntimeError(f"Optimization failed: {str(e)}")


def convert_schema(input_path: str, output_path: str, target_schema: str) -> None:
    """Convert ``input_path`` to ``target_schema`` using :mod:`ifcpatch`."""
    try:
        model = ifcopenshell.open(input_path)
        result = ifcpatch.execute({
            "input": input_path,
            "file": model,
            "recipe": "Migrate",
            "arguments": [target_schema]
        })
        if isinstance(result, ifcopenshell.file):
            result.write(output_path)
        else:
            raise RuntimeError("Unexpected output from ifcpatch")
    except Exception as e:
        raise RuntimeError(f"Schema conversion failed: {str(e)}")

def remove_empty_attributes(model):
    """Remove empty/default attributes by setting them to None using get_info()."""
    cleared = 0
    for entity in model:
        info = entity.get_info(include_identifier=False, recursive=False)
        for attr, value in info.items():
            if attr in ("id", "type"):
                continue
            if value in ("", None, 0, 0.0, "NOTDEFINED"):
                try:
                    if hasattr(entity, attr):
                        setattr(entity, attr, None)
                        cleared += 1
                except Exception as e:
                    print(f"Error clearing attribute '{attr}' on {entity}: {e}")
    return cleared

def remove_metadata(model):
    """Safer metadata removal - keeps at least one IfcOwnerHistory."""
    removed = 0
    owner_histories = model.by_type("IfcOwnerHistory")
    if owner_histories:
        for history in owner_histories[1:]:
            model.remove(history)
            removed += 1
    return removed

def remove_unused_spaces(model):
    spaces = model.by_type("IfcSpace")
    unused = []
    for space in spaces:
        if not any(
            ref for ref in model.get_inverse(space)
            if not ref.is_a(("IfcLocalPlacement", "IfcRelDefinesByProperties"))
        ):
            unused.append(space)
    for space in unused:
        model.remove(space)
    return len(unused)

def remove_unused_property_sets(model):
    psets = model.by_type("IfcPropertySet")
    removed = 0
    for pset in psets:
        if (not pset.HasProperties or len(pset.HasProperties) == 0) and not model.get_inverse(pset):
            try:
                for rel in model.get_inverse(pset):
                    if rel.is_a("IfcRelDefinesByProperties"):
                        model.remove(rel)
                model.remove(pset)
                removed += 1
            except Exception as e:
                print(f"Error removing property set: {e}")
    return removed

def remove_unused_materials(model):
    materials = model.by_type("IfcMaterial")
    removed = 0
    for material in materials:
        if not model.get_inverse(material):
            try:
                model.remove(material)
                removed += 1
            except Exception as e:
                print(f"Error removing material: {e}")
    return removed

def remove_unused_classifications(model):
    classifications = model.by_type("IfcClassificationReference")
    removed = 0
    for cls in classifications:
        if not model.get_inverse(cls):
            try:
                model.remove(cls)
                removed += 1
            except Exception as e:
                print(f"Error removing classification: {e}")
    return removed

def remove_small_elements(model, min_volume=0.001):
    removed = 0
    for element in model.by_type("IfcElement"):
        if element.Representation:
            try:
                vol = shape.get_volume(element)
                if vol and vol < min_volume:
                    model.remove(element)
                    removed += 1
            except Exception as e:
                print(f"Error checking volume: {e}")
    return removed

def remove_orphaned_entities(model):
    """
    Remove *truly* unreferenced objects but keep all
    spatial, containment and property-defining relations.
    """
    KEEP_REL = {
        "IfcRelContainedInSpatialStructure",
        "IfcRelAggregates",
        "IfcRelNests",
        "IfcRelDefinesByProperties",      # <- new
        "IfcRelDefinesByType",            # <- new (safe for types)
        "IfcRelAssigns",                  # generic assigns
        "IfcRelConnects",                 # connections
    }

    orphans = []
    for ent in model:
        t = ent.is_a()
        if t in ("IfcProject", "IfcOwnerHistory"):
            continue          # never delete
        if t.startswith("IfcRel") and any(t.startswith(k) for k in KEEP_REL):
            continue          # keep essential relations
        if not model.get_inverse(ent):
            orphans.append(ent)

    for ent in orphans:
        try:
            model.remove(ent)
        except Exception:
            pass
    return len(orphans)



def deduplicate_geometry(model) -> int:
    """Remove duplicate ``IfcShapeRepresentation`` objects."""

    geometry_map = {}
    duplicates = 0

    for shp in model.by_type("IfcShapeRepresentation"):
        key = hash(tuple(shp.Items))
        if key in geometry_map:
            try:
                for inv in model.get_inverse(shp):
                    replace_attribute(inv, shp, geometry_map[key])
                model.remove(shp)
                duplicates += 1
            except Exception as e:
                print(f"Error deduplicating geometry: {e}")
        else:
            geometry_map[key] = shp

    return duplicates

def flatten_spatial_structure(model) -> int:
    """Remove ``IfcSpatialStructureElement`` objects without contents."""

    removed = 0
    for spatial in model.by_type("IfcSpatialStructureElement"):
        if not spatial.ContainsElements:
            try:
                model.remove(spatial)
                removed += 1
            except Exception as e:
                print(f"Error removing spatial element: {e}")

    return removed

def remove_placeholder_properties(model, placeholder="-"):
    """
    Delete individual IfcPropertySingleValue objects whose NominalValue
    is exactly the *placeholder* string.  If a PropertySet ends up empty
    afterwards, remove the whole set (and its RelDefines link).

    Returns
    -------
    int  –  how many properties were deleted.
    """
    deleted = 0
    empty_psets = []

    for pset in model.by_type("IfcPropertySet"):
        props_to_keep = []
        for prop in pset.HasProperties:
            if (prop.is_a("IfcPropertySingleValue")
                and str(prop.NominalValue.wrappedValue).strip() == placeholder):
                # detach the property
                deleted += 1
            else:
                props_to_keep.append(prop)

        if props_to_keep:
            pset.HasProperties = props_to_keep
        else:
            empty_psets.append(pset)

    # remove empty property sets + their defining relations
    for pset in empty_psets:
        for rel in model.get_inverse(pset):
            if rel.is_a("IfcRelDefinesByProperties"):
                model.remove(rel)
        model.remove(pset)

    return deleted


def main() -> None:
    """Command line entry point."""

    import argparse

    parser = argparse.ArgumentParser(description="Optimize IFC files")
    parser.add_argument("input", help="Input IFC file")
    parser.add_argument("output", help="Output IFC file")

    parser.add_argument("--convert-schema", metavar="SCHEMA")
    parser.add_argument("--lossy-rounding", type=int, metavar="PREC")
    parser.add_argument("--ifczip-compress", action="store_true")
    parser.add_argument("--merge-cartesian", action="store_true")
    parser.add_argument("--dedupe-property-sets", action="store_true")
    parser.add_argument("--dedupe-classifications", action="store_true")
    parser.add_argument("--remove-dash-props", action="store_true")
    parser.add_argument("--remove-unused-spaces", action="store_true")
    parser.add_argument("--remove-metadata", action="store_true")
    parser.add_argument("--remove-empty-attributes", action="store_true")
    parser.add_argument("--remove-unused-property-sets", action="store_true")
    parser.add_argument("--remove-unused-materials", action="store_true")
    parser.add_argument("--remove-unused-classifications", action="store_true")
    parser.add_argument("--remove-small-elements", type=float, metavar="VOLUME")
    parser.add_argument("--remove-orphaned-entities", action="store_true")
    parser.add_argument("--deduplicate-geometry", action="store_true")
    parser.add_argument("--flatten-spatial-structure", action="store_true")

    args = parser.parse_args()
    options = {k: v for k, v in vars(args).items() if k not in {"input", "output"} and v is not None}

    stats = optimize_ifc(args.input, args.output, options)

    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
