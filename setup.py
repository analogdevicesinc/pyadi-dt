from setuptools import setup, find_packages

setup(
    name="adidt",
    version="0.0.1",
    packages=find_packages(),
    include_package_data=True,
    # package_data={"adidt": ["templates/*.tmpl"]},
    package_data={"adidt": ["templates/*"]},
    py_modules=["adidt"],
    install_requires=["Click", "fdt", "fabric", "rich", "numpy", "jinja2"],
    entry_points={
        "console_scripts": [
            "adidtc = adidt.cli.main:cli",
        ],
    },
)
