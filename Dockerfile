FROM public.ecr.aws/lambda/python:3.12
COPY requirements-runtime.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt --target ${LAMBDA_TASK_ROOT}
COPY src ${LAMBDA_TASK_ROOT}/src
ENV GX_ANALYTICS_ENABLED=false
CMD ["src.validator.handler.handler"]
