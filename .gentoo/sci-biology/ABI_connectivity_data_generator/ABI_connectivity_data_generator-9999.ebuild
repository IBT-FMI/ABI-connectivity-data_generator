# Copyright 1999-2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

EAPI=6

DESCRIPTION="Virtual : Generate a packaged version of gene expressin data from the Allen Mouse Brain data portal"

SLOT="0"
KEYWORDS=""

RDEPEND="
	dev-python/numpy
	sci-libs/nibabel
	dev-python/pynrrd
	sci-biology/mouse-brain-atlases
	sci-libs/nipype
	"

elog "Experimental package which only handles dependencies."
elog "No files will be installed."
elog "Scripts have to executed manually inside the repository."
