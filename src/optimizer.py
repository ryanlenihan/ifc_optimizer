# optimizer.py  –  self-contained, no stray functions -------------------
import ifcopenshell
import os, time, traceback, re, gzip, shutil
from ifcopenshell.util import shape
from ifcopenshell.util.element import replace_attribute
import ifcpatch

# ---------- helpers ----------------------------------------------------
_PT_RE = re.compile(r"(IFCCARTESIANPOINT)\(\s*([^)]+)\)")

def apply_lossy_rounding(raw: str, prec: int) -> str:
    """Round all numbers in IFCCARTESIANPOINT to <prec> decimals."""
    def _round(m):
        coords = [c.strip() for c in m.group(2).split(",")]
        rounded = []
        for c in coords:
            try:
                rounded.append(str(round(float(c), prec)))
            except ValueError:
                rounded.append(c)
        return f"{m.group(1)}({','.join(rounded)})"
    return _PT_RE.sub(_round, raw)

def merge_cartesian_points(model):
    """Model-level merge of identical IfcCartesianPoint entities."""
    seen, dupes = {}, []
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

def model_level_dedupe(model, entity_type):
    """Generic merge of identical instances of <entity_type>."""
    seen, dupes = {}, []
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

def write_ifczip(src_ifc, dst_ifczip):
    with open(src_ifc, "rb") as fin, gzip.open(dst_ifczip, "wb") as fout:
        shutil.copyfileobj(fin, fout)

# -----------------------------------------------------------------------

def optimize_ifc(input_path, output_path, options=None):
    """Main entry point called from gui.py"""
    start = time.time()
    print("Loading:", input_path)
    
    original_size = os.path.getsize(input_path) / (1024 * 1024)
    
    try:
        # -------------------------------------------------------------------
        # 1. OPTIONAL schema conversion -------------------------------------
        if options and options.get("convert_schema"):
            tmp_schema = input_path + ".conv.ifc"
            convert_schema(input_path, tmp_schema, options["target_schema"])
            input_path = tmp_schema
        tmp_files = []

        # -------------------------------------------------------------------
        # 2. OPTIONAL lossy rounding (text level) ---------------------------
        if options and options.get("lossy_rounding"):
            prec = int(options["lossy_rounding"])
            with open(input_path, "r", encoding="utf-8") as f:
                raw = f.read()
            tmp_round = input_path + ".round.ifc"
            with open(tmp_round, "w", encoding="utf-8") as f:
                f.write(apply_lossy_rounding(raw, prec))
            tmp_files.append(tmp_round)
            input_path = tmp_round
        # -------------------------------------------------------------------

        # -------------------------------------------------------------------
        # 3. Load model ------------------------------------------------------
        model = ifcopenshell.open(input_path)
        initial_size = os.path.getsize(input_path)/(1024*1024)
        stats = {}

        # -------------------------------------------------------------------
        # 4. Model-level optimisations --------------------------------------
        if options.get("merge_cartesian", False):
            stats["merged_points"] = merge_cartesian_points(model)
        if options.get("dedupe_property_sets", False):
            stats["dup_psets"] = model_level_dedupe(model, "IfcPropertySet")
        if options.get("dedupe_classifications", False):
            stats["dup_class"] = model_level_dedupe(model, "IfcClassificationReference")
        if options.get("remove_dash_props", False):
            stats["dash_props"] = remove_placeholder_properties(model, "-")


        # Existing routines -------------------------------------------------
        if options.get("remove_unused_spaces", False):
            stats["spaces"] = remove_unused_spaces(model)
        if options.get("remove_metadata", False):
            stats["metadata"] = remove_metadata(model)
        if options.get("remove_empty_attributes", False):
            stats["empty_attrs"] = remove_empty_attributes(model)
        if options.get("remove_unused_property_sets", False):
            stats["psets_unused"] = remove_unused_property_sets(model)
        if options.get("remove_unused_materials", False):
            stats["materials_unused"] = remove_unused_materials(model)
        if options.get("remove_unused_classifications", False):
            stats["class_unused"] = remove_unused_classifications(model)
        if "remove_small_elements" in options:
            stats["small_elems"] = remove_small_elements(model, options["remove_small_elements"])
        if options.get("remove_orphaned_entities", False):
            stats["orphans"] = remove_orphaned_entities(model)
        if options.get("deduplicate_geometry", False):
            stats["dup_geo"] = deduplicate_geometry(model)
        if options.get("flatten_spatial_structure", False):
            stats["spatial"] = flatten_spatial_structure(model)

        # -------------------------------------------------------------------
        # 5. Write results --------------------------------------------------
        model.write(output_path)
        if options.get("ifczip_compress", False):
            write_ifczip(output_path, output_path + ".ifczip")

        # 6. Housekeeping ---------------------------------------------------
        for f in tmp_files:
            os.remove(f)
        if options and options.get("convert_schema"):
            os.remove(tmp_schema)

        # -------------------------------------------------------------------
        final_size = os.path.getsize(output_path)/(1024*1024)
        print(f"Optimised → {output_path}  ({initial_size:.2f} MB → {final_size:.2f} MB)")
        print("Stats:", stats)
        print("Time  :", f"{time.time()-start:.1f}s")
        
        return stats

        # -------------------------------------------------------------------
        final_size = os.path.getsize(output_path)/(1024*1024)
        print(f"Optimised → {output_path}  ({original_size:.2f} MB → {final_size:.2f} MB)")
        print("Stats:", stats)
        print("Time  :", f"{time.time()-start:.1f}s")
        return stats

    except Exception as e:
        traceback.print_exc()
        raise RuntimeError(f"Optimization failed: {str(e)}")


def convert_schema(input_path, output_path, target_schema):
    """Convert IFC schema using ifcpatch"""
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



def deduplicate_geometry(model):
    geometry_map = {}
    duplicates = 0
    for shape in model.by_type("IfcShapeRepresentation"):
        key = hash(tuple(shape.Items))
        if key in geometry_map:
            try:
                for inverse in model.get_inverse(shape):
                    ifcopenshell.util.element.replace_attribute(inverse, shape, geometry_map[key])
                model.remove(shape)
                duplicates += 1
            except Exception as e:
                print(f"Error deduplicating geometry: {e}")
        else:
            geometry_map[key] = shape
    return duplicates

def flatten_spatial_structure(model):
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
