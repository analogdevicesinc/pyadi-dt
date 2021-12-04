from setuptools import setup, find_packages

setup(
    name="adidt",
    version="0.0.1",
    packages=find_packages(),
    include_package_data=True,
    py_modules=["adidt"],
    install_requires=["Click", "fdt", "fabric", "rich", "numpy", "xmltodict"],
    entry_points={
        "console_scripts": [
            "adidtc = adidt.cli.main:cli",
        ],
    },
)
