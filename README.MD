# IFC Optimizer

A tool for Axis Soluções em Engenharia to optimize and reduce the size of IFC files for faster sharing, easier collaboration, and improved BIM workflows.

## Features

- 🚀 **Remove unused IFC spaces, property sets, materials, and classifications**
- 🧹 **Clean up orphaned entities and empty/default attributes**
- 🗜️ **Deduplicate geometry and flatten spatial structure**
- ✂️ **Remove small elements by customizable volume threshold**
- 🔄 **Optional schema conversion (e.g., IFC4.3 → IFC2X3)**
- 📊 **Detailed optimization statistics and file size reduction report**
- 🖥️ **Modern, user-friendly GUI (PySide6) and CLI support**
- ⏳ **Progress bar and custom icon**

## Install

1. **Clone or download this repository**
2. **Install requirements** (Python 3.12 recommended)

## How It Works

**IFC Optimizer** analyzes your IFC file, removes redundant or unused data, merges duplicate geometry, and can convert the schema version for maximum compatibility.  
This often reduces file size by **30–70%** for most models.

## References & Inspiration

- [IfcOpenShell Optimizer Tutorial](https://academy.ifcopenshell.org/posts/ifcopenshell-optimizer-tutorial/)
- [IFCCompressor: A content-based compression algorithm](https://yushen-liu.github.io/IFCCompressor/index.html)
- [Simplebim Model Optimization](https://support.simplebim.com/04-clean-up-models/)
- [Bentley IFC Optimizer](https://docs.bentley.com/LiveContent/web/AECOsim%20Building%20Designer%20Help-v5/en/GUID-3CB7A5B3-5A2E-48E2-9116-E0B041AEF934.html)
