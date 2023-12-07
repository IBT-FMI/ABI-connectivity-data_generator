# Copyright 1999-2023 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

EAPI=8

DESCRIPTION="Generate gene expression data from the Allen Mouse Brain data portal"
HOMEPAGE="https://bitbucket.org/TheChymera/opfvta"

LICENSE="GPL-3"
SLOT="0"
KEYWORDS=""

DEPEND=""
RDEPEND="
	dev-python/numpy
	sci-libs/nibabel
	dev-python/pynrrd
	sci-biology/mouse-brain-templates
	sci-libs/nipype
"
