# Use Python base image
FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY scripts/ scripts/
COPY config/ config/
COPY events/ events/
COPY *.py ./

# Set default output directory for feeds
ENV FEEDS_DIR=/app/docs/feeds

# Create the feeds directory
RUN mkdir -p ${FEEDS_DIR}

# Default command: run the splitter
CMD ["python", "scripts/split_personal_ics.py"]
