# ecotaxa_ML_back

Machine Learning dedicated backend for EcoTaxa.

## Project Overview

This project provides a specialized backend for [EcoTaxa](https://github.com/ecotaxa/ecotaxa), focused on computationally intensive Machine Learning (ML) tasks. It is designed to run on infrastructure equipped with GPUs to handle deep learning operations efficiently.

## Roles and Separation

The EcoTaxa ecosystem is split into multiple components:
- **EcoTaxa Front/Main Backend**: Handles user authentication, metadata management, project organization, and the web interface.
- **EcoTaxa ML Backend (this project)**: Specifically handles ML-related background jobs.

By separating these roles, the main EcoTaxa application remains responsive while heavy ML tasks (like deep feature extraction or Random Forest training/prediction) are offloaded to dedicated GPU-enabled nodes.

## Architecture and Interface

This project does not provide a direct REST API for users. Instead, it interacts with the rest of the system through:

1.  **Shared Database**: It connects to the same PostgreSQL database as the main EcoTaxa backend.
2.  **Job Queue**: It monitors the `job` table in the database for tasks of specific types (e.g., `Prediction`).
3.  **Job Runner**: The `ml_jobs_runner.py` script acts as a background worker. It polls the database for pending jobs that require GPU acceleration, executes them, and updates their status and results directly in the database.

## Key Operations

The primary ML pipeline implemented here includes:
- **Deep Feature Extraction**: Using pre-trained Convolutional Neural Networks (CNN) to extract high-dimensional features from images.
- **Dimensionality Reduction**: Reducing these features (e.g., via PCA) to a manageable size for storage and classification.
- **Classification**: Training Random Forest classifiers on labeled data and predicting classes for unlabeled images.

For more details on the ML process, see [src/ML/README.md](src/ML/README.md).
For development setup, see [README_dev.md](README_dev.md).
