from setuptools import find_packages, setup

setup(
    name="adidt",
    version="0.0.1",
    packages=find_packages(),
    include_package_data=True,
    package_data={"adidt": ["templates/*.tmpl"]},
    py_modules=["adidt"],
    install_requires=["Click", "fdt", "fabric", "rich", "numpy", "xmltodict"],
    entry_points={"console_scripts": ["adidtc = adidt.cli.main:cli",],},
)
