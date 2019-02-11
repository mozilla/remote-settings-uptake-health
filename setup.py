from setuptools import setup, find_packages
from pathlib import Path


CURRENT_DIR = Path(__file__).parent


def get_long_description():
    with open(CURRENT_DIR / "README.md") as f:
        return f.read()


setup(
    name="remote-settings-uptake-worrying",
    version="0.0.0",
    author="Product Delivery",
    url="https://github.com/XXXX",
    description="You OK Remote Settings Uptake Telemetry?",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    license="MPL 2.0",
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: Implementation :: CPython",
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
    ],
    python_requires=">=3.6",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=["requests", "python-decouple", "toml", "click"],
    extras_require={
        "dev": ["tox", "twine", "therapist", "black", "flake8", "requests_cache"]
    },
)
