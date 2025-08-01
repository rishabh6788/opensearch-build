# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

# This is a docker image specifically for standardize the ci/cd environment
# for both developers and ci/cd tools in OpenSearch / OpenSearch-Dashboards
# Please read the README.md file for all the information before using this dockerfile


FROM almalinux:8

ARG MAVEN_DIR=/usr/local/apache-maven
ARG CONTAINER_USER=ci-runner
ARG CONTAINER_USER_HOME=/home/ci-runner

# Ensure localedef running correct with root permission
USER 0

# Add normal dependencies
RUN dnf clean all && dnf install -y 'dnf-command(config-manager)' && \
    dnf update -y && \
    dnf install -y which curl git gnupg2 tar net-tools procps-ng python39 python39-devel python39-pip zip unzip jq

# Replace default curl 7.61.1 on Almalinux8 with 7.75+ version to support aws-sigv4
# https://github.com/curl/curl/commit/08e8455dddc5e48e58a12ade3815c01ae3da3b64
# https://curl.se/changes.html#7_75_0
RUN ARCH=`uname -m`; \
    if [ "$ARCH" = "ppc64le" ]; then ARCH=powerpc64le; fi; \
    curl -SfL https://github.com/stunnel/static-curl/releases/download/8.6.0-1/curl-linux-$ARCH-8.6.0.tar.xz -o curl.tar.xz && \
    tar -xvf curl.tar.xz && \
    mv -v curl /usr/local/bin/curl && \
    rm -v curl.tar.xz && \
    cd /etc/ssl/certs && ln -s ca-bundle.crt ca-certificates.crt

# Create user group
RUN groupadd -g 1000 $CONTAINER_USER && \
    useradd -u 1000 -g 1000 -d $CONTAINER_USER_HOME $CONTAINER_USER && \
    mkdir -p $CONTAINER_USER_HOME && \
    chown -R 1000:1000 $CONTAINER_USER_HOME

# Add Python dependencies
RUN dnf install -y @development zlib-devel bzip2 bzip2-devel readline-devel sqlite sqlite-devel openssl-devel xz xz-devel libffi-devel findutils

# Add Dashboards dependencies
RUN dnf install -y xorg-x11-server-Xvfb gtk2-devel gtk3-devel libnotify-devel GConf2 nss libXScrnSaver alsa-lib

# Add Notebook dependencies
RUN dnf install -y nss xorg-x11-fonts-100dpi xorg-x11-fonts-75dpi xorg-x11-utils xorg-x11-fonts-cyrillic xorg-x11-fonts-Type1 xorg-x11-fonts-misc fontconfig freetype && dnf clean all

# Add Yarn dependencies
RUN dnf groupinstall -y "Development Tools" && dnf clean all && rm -rf /var/cache/dnf/*

# Tools setup
COPY --chown=0:0 config/jdk-setup.sh config/yq-setup.sh config/gh-setup.sh config/op-setup.sh /tmp/
RUN dnf install -y go && /tmp/jdk-setup.sh && /tmp/yq-setup.sh && /tmp/gh-setup.sh && /tmp/op-setup.sh

# Install higher version of maven 3.8.x
RUN export MAVEN_URL=`curl -s https://maven.apache.org/download.cgi | grep -Eo '["\047].*.bin.tar.gz["\047]' | tr -d '"' | uniq | head -n 1`  && \
    mkdir -p $MAVEN_DIR && (curl -s $MAVEN_URL | tar xzf - --strip-components=1 -C $MAVEN_DIR) && \
    echo "export M2_HOME=$MAVEN_DIR" > /etc/profile.d/maven_path.sh && \
    echo "export M2=\$M2_HOME/bin" >> /etc/profile.d/maven_path.sh && \
    echo "export PATH=\$M2:\$PATH" >> /etc/profile.d/maven_path.sh && \
    ln -sfn $MAVEN_DIR/bin/mvn /usr/local/bin/mvn

# Setup Shared Memory
RUN chmod -R 777 /dev/shm

# Install PKG builder dependencies with rvm
RUN curl -sSL https://rvm.io/mpapis.asc | gpg2 --import - && \
    curl -sSL https://rvm.io/pkuczynski.asc | gpg2 --import - && \
    curl -sSL https://get.rvm.io | bash -s stable

# Switch shell for rvm related commands
SHELL ["/bin/bash", "-lc"]
CMD ["/bin/bash", "-l"]

# Install ruby / rpm / fpm related dependencies
RUN . /etc/profile.d/rvm.sh && rvm install 2.6.0 && rvm --default use 2.6.0 && dnf install -y rpm-build rpm-sign createrepo pinentry && dnf clean all

ENV RUBY_HOME=/usr/local/rvm/rubies/ruby-2.6.0/bin
ENV RVM_HOME=/usr/local/rvm/bin
ENV GEM_HOME=$CONTAINER_USER_HOME/.gem
ENV GEM_PATH=$GEM_HOME
ENV PATH=$RUBY_HOME:$RVM_HOME:$PATH

# Install Python binary
RUN update-alternatives --set python /usr/bin/python3.9 && \
    update-alternatives --set python3 /usr/bin/python3.9 && \
    pip3 install pip==23.1.2 && pip3 install pipenv==2023.6.12 awscli==1.32.17

# Add k-NN Library dependencies
# EL8 requires install config-manager and enable powertools to consume openblas-static
RUN dnf install -y 'dnf-command(config-manager)' && \
    dnf config-manager --set-enabled powertools && \
    dnf install epel-release -y && dnf repolist && \
    dnf install openblas-static lapack gcc-gfortran -y && dnf clean all
RUN pip3 install cmake==3.26.4
# Upgrade gcc
# The setup part is partially based on Austin Dewey's article:
# https://austindewey.com/2019/03/26/enabling-software-collections-binaries-on-a-docker-image/
RUN dnf -y install gcc-toolset-11-gcc gcc-toolset-11-gcc-c++ && dnf clean all && \
    echo "source /opt/rh/gcc-toolset-11/enable" > /etc/profile.d/gcc-toolset-11.sh
COPY --chown=0:0 config/gcc-toolset-11-setup /usr/local/bin/gcc_setup
ENV BASH_ENV="/usr/local/bin/gcc_setup"
ENV ENV="/usr/local/bin/gcc_setup"
ENV PROMPT_COMMAND=". /usr/local/bin/gcc_setup"

# Change User
USER $CONTAINER_USER
WORKDIR $CONTAINER_USER_HOME

# Install fpm for opensearch dashboards core
RUN gem install dotenv -v 2.8.1 && gem install public_suffix -v 5.1.1 && gem install rchardet -v 1.8.0 && gem install fpm -v 1.14.2
ENV PATH=$CONTAINER_USER_HOME/.gem/gems/fpm-1.14.2/bin:$PATH
RUN fpm -v
