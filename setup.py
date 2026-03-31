from setuptools import setup

if __name__ == "__main__":
    setup(
        name="CrocoDash",
        packages=["CrocoDash"],
        version="0.1",
        package_dir={"CrocoDash": "CrocoDash"},
        entry_points={
            "console_scripts": [
                "crocodash=CrocoDash.cli:main",
            ],
        },
    )
