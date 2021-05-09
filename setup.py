import setuptools

setuptools.setup(
    use_scm_version={"write_to": "pymmcore_remote/_version.py"},
    setup_requires=["setuptools_scm"],
)
