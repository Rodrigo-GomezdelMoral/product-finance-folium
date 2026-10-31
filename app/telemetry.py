import logging
from os import environ

from azure.identity import DefaultAzureCredential
from azure.monitor.opentelemetry import configure_azure_monitor

LOGGER = logging.getLogger("folium")


def configure() -> None:
    LOGGER.setLevel(logging.INFO)
    if "APPLICATIONINSIGHTS_CONNECTION_STRING" in environ:
        configure_azure_monitor(
            credential=DefaultAzureCredential(), logger_name="folium", enable_trace_based_sampling_for_logs=False
        )


def event(name: str, **properties: object) -> None:
    LOGGER.info(name, extra={"microsoft.custom_event.name": name} | properties)
