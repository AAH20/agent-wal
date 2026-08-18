from setuptools import setup, find_packages

setup(
    name="agent-wal",
    version="1.0.0",
    description="The Embedded Write-Ahead Logging (WAL) & Deterministic Replay Engine for AI Agents",
    author="Ahmed Hassan",
    author_email="ahmed.alaa.hassan25@gmail.com",
    packages=find_packages(),
    python_requires=">=3.8",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
