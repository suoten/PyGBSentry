from setuptools import setup, Extension
from Cython.Build import cythonize

extensions = [
    Extension(
        "app.core._license_native._verify",
        ["verify.pyx"],
    )
]

setup(
    name="_license_native",
    ext_modules=cythonize(
        extensions,
        compiler_directives={"language_level": "3"},
    ),
)
