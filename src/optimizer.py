import ifcopenshell
import os
import sys
import time
import traceback
from ifcopenshell.util import shape, representation
import ifcpatch

def optimize_ifc(input_path, output_path, options=None):
    """Optimize IFC file with selected options."""
    print(f"Loading IFC file: {input_path}")
    start_time = time.time()
    
    try:
        # Schema conversion (if enabled)
        if options and options.get("convert_schema"):
            temp_path = "temp_converted.ifc"
            convert_schema(input_path, temp_path, options["target_schema"])
            input_path = temp_path

        # Load the (possibly converted) model
        model = ifcopenshell.open(input_path)
        
        # Default options if none provided
        if options is None:
            options = {
                'remove_unused_spaces': True,
                'remove_metadata': True,
                'remove_empty_attributes': True,
                'remove_unused_property_sets': True,
                'remove_unused_materials': True,
                'remove_unused_classifications': True,
                'remove_small_elements': 0.001,
                'remove_orphaned_entities': True,
                'deduplicate_geometry': True,
                'flatten_spatial_structure': True
            }

        initial_size = os.path.getsize(input_path) / (1024 * 1024)
        print(f"Initial file size: {initial_size:.2f} MB")
        
        # Perform optimizations
        stats = {}
        if options.get('remove_unused_spaces', False):
            stats['spaces'] = remove_unused_spaces(model)
        if options.get('remove_metadata', False):
            stats['metadata'] = remove_metadata(model)
        if options.get('remove_empty_attributes', False):
            stats['empty_attrs'] = remove_empty_attributes(model)
        if options.get('remove_unused_property_sets', False):
            stats['psets'] = remove_unused_property_sets(model)
        if options.get('remove_unused_materials', False):
            stats['materials'] = remove_unused_materials(model)
        if options.get('remove_unused_classifications', False):
            stats['classifications'] = remove_unused_classifications(model)
        if 'remove_small_elements' in options:
            min_vol = options['remove_small_elements']
            stats['small_elements'] = remove_small_elements(model, min_vol)
        if options.get('remove_orphaned_entities', False):
            stats['orphans'] = remove_orphaned_entities(model)
        if options.get('deduplicate_geometry', False):
            stats['duplicate_geo'] = deduplicate_geometry(model)
        if options.get('flatten_spatial_structure', False):
            stats['spatial'] = flatten_spatial_structure(model)

        model.write(output_path)

        # Cleanup temp file if conversion was done
        if options and options.get('convert_schema', False):
            os.remove(temp_path)

        # Validation and results
        print("Validating optimized file...")
        test_model = ifcopenshell.open(output_path)
        print("Validation successful.")

        final_size = os.path.getsize(output_path) / (1024 * 1024)
        print(f"\nOptimization removed:")
        for key, value in stats.items():
            print(f"- {value} {key.replace('_', ' ')}")
        print(f"\nFinal size: {final_size:.2f} MB")
        print(f"Size reduction: {initial_size - final_size:.2f} MB ({(1 - final_size/initial_size)*100:.2f}%)")
        print(f"Time taken: {time.time() - start_time:.2f}s")

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
    orphans = []
    for entity in model:
        if entity.is_a() in ["IfcProject", "IfcOwnerHistory"]:
            continue
        if not model.get_inverse(entity):
            orphans.append(entity)
    for entity in orphans:
        try:
            model.remove(entity)
        except Exception as e:
            print(f"Error removing orphan: {e}")
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
