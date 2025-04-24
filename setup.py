from setuptools import setup, find_packages

setup(
    name="ifc_optimizer",
    version="0.1.0",
    description="A tool to reduce IFC file sizes",
    author="Willian D.",
    author_email="your@email.com",  # <-- Put your email here
    maintainer="Axis Soluções em Engenharia",
    maintainer_email="contato@axissolucoes.com.br",  # <-- Or your company email
    long_description="A tool by Axis Soluções em Engenharia to optimize and reduce the size of IFC files.",
    long_description_content_type="text/plain",
    url="https://axissolucoes.com.br",  # <-- Or your project/company URL
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "ifcopenshell",
    ],
    entry_points={
        "console_scripts": [
            "ifc-optimize=src.optimizer:main",
        ],
    },
    python_requires=">=3.6",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "Intended Audience :: End Users/Desktop",
        "Intended Audience :: Developers",
        "Natural Language :: Portuguese",
        "License :: OSI Approved :: MIT License",  # or your license
    ],
    project_urls={
        "Company": "https://axissolucoes.com.br",
        "Source": "https://github.com/yourusername/ifc_optimizer",
    },
)
