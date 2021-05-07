FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get install -y python-dev samtools liblzma-dev libbz2-dev zlib1g-dev liblzo2-dev python3-pip && \
    pip3 install scipy && \ 
    pip3 install smallrnaseq && \ 
    apt-get install -y bowtie && \
    apt-get install -y r-base && \
    R -e 'install.packages("BiocManager"); BiocManager::install("edgeR")'