"""Utilities to work with Gemini models."""

import os

from google.adk.models.google_llm import Gemini
from google.genai import Client


def get_geofenced_gemini_model(
    project_id: str | None = None, location: str | None = None, model: str | None = None
) -> Gemini:
    """Creates (by patching) a gemini model in the given GCP location."""
    project_id = project_id or os.environ.get(
        "GOOGLE_CLOUD_PROJECT", "msteiner-kubeflow"
    )
    location = location or os.environ.get("GOOGLE_CLOUD_LOCATION", "europe-west4")
    model = model or "gemini-2.5-flash"
    client = Client(
        vertexai=True,
        project=project_id,
        location=location,
    )

    model_instance = Gemini(model=model)
    model_instance.api_client = client
    return model_instance
