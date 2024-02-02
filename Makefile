# We must allow others exactly use our script without modification
# Or its not replicable by others.
#
REGISTRY=docker.io
REPOSITORY=centerforopenneuroscience

IMAGE_NAME=abi-connectivity
IMAGE_TAG=0.0.1

FQDN_IMAGE=${REGISTRY}/${REPOSITORY}/${IMAGE_NAME}:${IMAGE_TAG}

# PATH for scratch directory storing intermidiate results etc;
# By default -- all data including intermediate results are under this folder (YODA!)

OCI_BINARY?=podman
RELEASE_VERSION?=9999
RESOLUTION?=100 # specified in microns
SING_BINARY?=singularity
PACKAGE_NAME=ABI-connectivity-data

DISTFILE_CACHE_CMD :=

check_defined = \
	$(strip $(foreach 1,$1, \
		$(call __check_defined,$1,$(strip $(value 2)))))
__check_defined = \
	$(if $(value $1),, \
	  $(error Undefined $1$(if $2, ($2))))

ifeq ($(DISTFILE_CACHE_PATH),)
	# If not set, don't add it as an option
else
	DISTFILE_CACHE_CMD =-v $(DISTFILE_CACHE_PATH):/var/cache/distfiles
endif

.PHONY: bidsdata
bidsdata:
	python code/abi_connectivity.py \
		--version=${RELEASE_VERSION} \
		--resolution=${RESOLUTION} \
		--bids-only

.PHONY: bidsdata-oci
bidsdata-oci:
	$(OCI_BINARY) run \
		-it \
		--rm \
		-v ${PWD}:/root/src/ABI-connectivity \
		--workdir /root/src/ABI-connectivity \
		${FQDN_IMAGE} \
		make bidsdata

.PHONY: sourcedata
sourcedata: clean
	python code/abi_connectivity.py \
		--version=${RELEASE_VERSION} \
		--resolution=${RESOLUTION} \
		--download-only

.PHONY: sourcedata-oci
sourcedata-oci: clean
	$(OCI_BINARY) run \
		-it \
		--rm \
		-v ${PWD}:/root/src/ABI-connectivity \
		--workdir /root/src/ABI-connectivity \
		${FQDN_IMAGE} \
		make sourcedata

.PHONY: procdata
procdata:
	python code/abi_connectivity.py \
		--version=${RELEASE_VERSION} \
		--resolution=${RESOLUTION} \
		--process-only

.PHONY: procdata-oci
procdata-oci:
	$(OCI_BINARY) run \
		-it \
		--rm \
		-v ${PWD}:/root/src/ABI-connectivity \
		--workdir /root/src/ABI-connectivity \
		${FQDN_IMAGE} \
		make procdata

.PHONY: data
data:
	python code/abi_connectivity.py \
		--version=${RELEASE_VERSION} \
		--resolution=${RESOLUTION}

.PHONY: data-oci
data-oci:
	$(OCI_BINARY) run \
		-it \
		--rm \
		-v ${PWD}:/root/src/ABI-connectivity \
		--workdir /root/src/ABI-connectivity \
		${FQDN_IMAGE} \
		make data

.PHONY: data-oci-interactive
data-oci-interactive: clean
	$(OCI_BINARY) run \
		-it \
		--rm \
		-v ${PWD}:/root/src/ABI-connectivity \
		--workdir /root/src/ABI-connectivity \
		${FQDN_IMAGE} \
		/bin/bash



# Build data analysis container
.PHONY: oci-image
oci-image:
	$(OCI_BINARY) build . $(DISTFILE_CACHE_CMD) \
		-f code/Containerfile \
		-t ${FQDN_IMAGE}

# Push containers
.PHONY: oci-push
oci-push:
	$(OCI_BINARY) push ${FQDN_IMAGE}

# Push containers
.PHONY: clean
clean:
	@rm -rf sourcedata/*



