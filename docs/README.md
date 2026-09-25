# Documentation

Guides for running and understanding SermonPilot.

- [RELEASES.md](RELEASES.md): operator-facing release notes and upgrade notes.
- [DEPLOYMENT.md](DEPLOYMENT.md): deploy the published container image with Docker Compose, the environment and volumes, and end-to-end verification.
- [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md): install from source with uv or pip and choose a requirements file for your hardware.
- [GPU_INSTALLATION.md](GPU_INSTALLATION.md): CUDA and ROCm setup for GPU acceleration.
- [UV_SETUP.md](UV_SETUP.md): using uv to manage the Python environment.
- [AUTO_EDIT.md](AUTO_EDIT.md): cut detection, the keeper transcode, and the review workflow.
- [UPLOAD_EXISTING_RENDER.md](UPLOAD_EXISTING_RENDER.md): publish a render that is already on disk without rendering again.
- [CANCELLATION.md](CANCELLATION.md): how cancelling a job stops the running work, and how restart reconciliation clears stuck rows.
- [DELETION_POLICY.md](DELETION_POLICY.md): every media delete is a recoverable move, and cloud media stays on its remote.
- [SERMON_IDENTITY.md](SERMON_IDENTITY.md): how a sermon id is derived so re-runs upsert one row.
- [SETTINGS_PARITY.md](SETTINGS_PARITY.md): how each legacy Streamlit setting maps to the web console.
- [LLM_Configuration_Guide.md](LLM_Configuration_Guide.md): LLM providers, models, and endpoints.
- [CLOUD_MOUNTS_OAUTH.md](CLOUD_MOUNTS_OAUTH.md): bring your own Google OAuth client for cloud mounts.
- [DESCRIPTION_FAILURE_HANDLING.md](DESCRIPTION_FAILURE_HANDLING.md): description generation returns usable prose or raises, never a failure string.
- [DESCRIPTION_VALIDATION_FEATURE.md](DESCRIPTION_VALIDATION_FEATURE.md): checking and regenerating existing descriptions.
- [SECURITY_SETUP_GUIDE.md](SECURITY_SETUP_GUIDE.md): credential management, UI password protection, and the pre-commit scanner.
- [ANALYTICS.md](ANALYTICS.md): the Streamlit Analytics page (legacy UI).
- [PERFORMANCE_MONITORING.md](PERFORMANCE_MONITORING.md): the performance monitor and the metrics it collects.
- [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md): older Streamlit-era production notes (bare metal, systemd, an nginx upstream to 8501); use DEPLOYMENT.md for the container flow.
