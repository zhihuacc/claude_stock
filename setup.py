from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="claude_stock",
    version="0.1.0",
    packages=find_packages(),
    install_requires=install_requires,
)
