FROM ubuntu:latest
LABEL authors="kang"

ENTRYPOINT ["top", "-b"]