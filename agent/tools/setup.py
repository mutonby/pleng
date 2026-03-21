from setuptools import setup

setup(
    name="pleng-cli",
    version="0.1.0",
    py_modules=["pleng"],
    entry_points={"console_scripts": ["pleng=pleng:main"]},
    install_requires=["requests"],
)
