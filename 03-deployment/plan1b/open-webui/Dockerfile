FROM ghcr.io/open-webui/open-webui:v0.9.6

COPY instrument_batches.py /tmp/instrument_batches.py
RUN python /tmp/instrument_batches.py && rm -v /tmp/instrument_batches.py
