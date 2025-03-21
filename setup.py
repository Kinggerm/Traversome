#!/usr/bin/env python

"""
Install the traversome package.

Local install for developers:
    conda install python numpy scipy sympy python-symengine dill typer loguru -c conda-forge
    pip install . -e --no-deps
"""

import os
import re
from setuptools import setup

# parse version from init.py
with open("traversome/__init__.py") as init:
    CUR_VERSION = re.search(
        r"^__version__ = ['\"]([^'\"]*)['\"]",
        init.read(),
        re.M,
    ).group(1)


# nasty workaround for RTD low memory limits
on_rtd = os.environ.get('READTHEDOCS') == 'True'
if on_rtd:
    install_requires = []
else:
    install_requires = [
        "dill",
        "numpy",
        "scipy",
        "symengine",
        "sympy",
        # "pymc>=4",  # make mcmc optional
        # "matplotlib",
        "typer",
        "loguru",
    ]


# setup installation
setup(
    name="traversome",
    packages=["traversome"],
    version=CUR_VERSION,
    author="Jianjun Jin",
    author_email="...",
    install_requires=install_requires,
    entry_points={
        'console_scripts': ['traversome = traversome.__main__:app']},
    license='GPL',
    classifiers=[
        'Programming Language :: Python :: 3',
    ],
)
