import argparse
import copy
import json
import os
import glob
import sys
import urllib
import urllib.request
import shutil
import zipfile
import numpy
import nibabel
import tarfile
import re
import nrrd
import xml.etree.ElementTree as et
from collections import defaultdict
from nipype.interfaces.ants import ApplyTransforms
from nipype.interfaces.ants.base import ANTSCommand, ANTSCommandInputSpec
from nipype.interfaces.base import BaseInterface, BaseInterfaceInputSpec, traits, File, Str, TraitedSpec, Directory, CommandLineInputSpec, CommandLine, InputMultiPath, isdefined, Bunch, OutputMultiPath

#from nipype.interfaces.fsl import fslorient

API_SERVER = "http://api.brain-map.org/"
API_DATA_PATH = API_SERVER + "api/v2/data/"

def GetExpID(startRow=0,numRows=2000,totalRows = -1):
	"""
	Queries the Allen Mouse Brain Institute website for all gene expression data available for download.

	Returns:
	--------
	GeneNames: list[dict()]
		list of all genes where expression data is available for download. Dict contains experiment/gene metadata.

	SectionDataSetID : list(int)
		corresponding SectionDataSetID (SectionDataSet: see "http://help.brain-map.org/display/api/Data+Model")
		ID needed to specify download target.

	"""

	startRow = startRow
	numRows = numRows
	totalRows = totalRows
	rows = []
	GeneNames = []
	SectionDataSetID = []
	info = list()
	done = False

	while not done:
		r = "&start_row={0}&num_rows={1}".format(startRow,numRows)
		pagedUrl = API_DATA_PATH + "query.json?criteria=model::SectionDataSet,rma::criteria,products%5Bid$eq5%5D,rma::include,specimen(stereotaxic_injections(primary_injection_structure,structures))" + r
		source = urllib.request.urlopen(pagedUrl).read()
		response = json.loads(source)
		rows += response['msg']
		for x in response['msg']:

			if x['failed'] == False :
				print(x['id'])
				info.append(x['id'])
		if totalRows < 0:
			totalRows = int(response['total_rows'])

		startRow += len(response['msg'])

		if startRow >= totalRows:
			done = True

	return info


def nrrd_to_nifti(file):
	print("Reading " + file)
	readnrrd = nrrd.read(file)
	data = readnrrd[0]
	header = readnrrd[1]
	print(header)
	print("Converting " + file)

	affine_matrix = numpy.array(header["space directions"],dtype=float)
	affine_matrix = affine_matrix*0.001
	affine_matrix = numpy.insert(affine_matrix,3,[0,0,0], axis=1)
	affine_matrix = numpy.insert(affine_matrix,3,[0,0,0,1], axis=0)

	#Change Orientation from PIR to RAS. Steps: PIR -> RIP -> RPI -> RPS -> RAS
	data.setflags(write=1)
	data = numpy.swapaxes(data,0,2)
	data = numpy.swapaxes(data,1,2)
	data = data[:,:,::-1]
	data = data[:,::-1,:]
	data = data[::-1,:,:] #TODO: Check for Atlas files!!!!!!
	img = nibabel.Nifti1Image(data,affine_matrix)
	nii_path = os.path.join(os.path.dirname(file), os.path.basename(file).split(".")[0] + '.nii')
	nibabel.save(img,nii_path)

	return nii_path

def get_identifying_structure(metadata):
	tree = et.parse(metadata)
	root = tree.getroot()
	struc = root.findall('.//primary-injection-structure/safe-name')[0]
	return struc.text

def get_exp_metadata(exp,path):
	url_meta = API_DATA_PATH + "/SectionDataSet/query.xml?id=" + str(exp) + "&include=specimen(stereotaxic_injections(primary_injection_structure,structures))"
	filename = str(exp) + "_experiment_metadata.xml"
	s = urllib.request.urlopen(url_meta)
	contents = s.read()
	path_to_metadata = os.path.join(path,filename)
	file = open(path_to_metadata, 'wb')
	file.write(contents)
	file.close()

	return path_to_metadata


def download_all_connectivity(info,folder_name,resolution=200):
	"""
	Download all given genes corresponding to SectionDataSetID given in 100um and 25um resolution, converts nrrd to nii, registers to dsurqec... and resamples files to 40 and 200 respectively.

	Parameters:
	-----------
	SectionDataSetID : list(int)
		o=[0.200000002980232 0 0 -6.26999998092651; 0 0.200000002980232 0 -10.6000003814697; 0 0 0.200000002980232 -7.88000011444092; 0 0 0 1]list of SectionDataSetID to download.
	"""
	print(resolution==200)
	if resolution is None:
		res=[100,25]
	elif resolution==40:
		res=[25]
	elif resolution==200:
		res=[100]
		print(res)
	else:
		res = [99]
	print(resolution)
	download_url = "http://api.brain-map.org/grid_data/download_file/"
	print(res)
	for resolution in res:
		if resolution == 100: path_to_res = folder_name
		if resolution == 25: path_to_res = folder_name + "HD"
		if not os.path.isdir(path_to_res):os.mkdir(path_to_res)
		for exp in info:
			path_to_exp = os.path.join(path_to_res,str(exp))
			#TODO: look inside if stuff is there...
			os.mkdir(path_to_exp)
			path_to_metadata = get_exp_metadata(exp,path_to_exp) #TODO: so far no coordinate info. Also, avoid downloading twice
			struc_name=get_identifying_structure(path_to_metadata)
			struc_name = struc_name.lower()
			struc_name= re.sub(" ","_",struc_name)
			struc_name=re.sub("[()]","",struc_name)
			new_name = struc_name + "-" + os.path.basename(path_to_exp)
			new_path = os.path.join(os.path.dirname(path_to_exp),new_name)
			os.rename(path_to_exp,new_path)
			resolution_url = "?image=projection_density&resolution=" + str(resolution)
			url = download_url + str(exp) + resolution_url
			fh = urllib.request.urlretrieve(url)
			filename = str.split((fh[1]._headers[6][1]),'filename=')[1] #TODO: Consistent??
			#TODO: do that differenttly ...
			filename = str.split(filename,";")[0]
			file_path_nrrd = os.path.join(new_path,filename)
			shutil.copy(fh[0],file_path_nrrd)
			os.remove(fh[0])
			#os.rename(fh[0],file_path_nrrd) only works if source and dest are on the same filesystem
			file_path_nii = nrrd_to_nifti(file_path_nrrd)
			os.remove(file_path_nrrd)
			file_path_2dsurqec = apply_composite(file_path_nii,resolution)
			os.remove(file_path_nii)
			#create archives

		if resolution == 25:
			sort_and_archive()

		elif resolution == 100:
			save_info(info,folder_name)
			tarname=folder_name + ".tar.xz"
			create_archive(tarname,folder_name)

	return

def apply_composite(file,resolution):
	#TODO: does this downsample if composite file is low resolution? Currently composite file is 40um. If it does,is it a problem? Target resolution is 40 anyway, but maybe get a
	#composite file at 25um as well? ResampleImage is possibly not needed otherwise, just specify reference image resolution of 40 and 200
	"""
	Uses ANTS ApplyTransforms to register image to

	Parameters :
	------------

	file : str
		path to image

	"""
	at = ApplyTransforms()
	at.inputs.dimension = 3
	at.inputs.input_image = file
	if resolution == 100:
		ref_image = '/usr/share/mouse-brain-atlases/dsurqec_200micron_masked.nii'
		resolution = 200
	else:
		ref_image = '/usr/share/mouse-brain-atlases/dsurqec_40micron_masked.nii'
		resolution = 40

	#TODO: theres got to be an easier way...
	output_image = ""
	for s in os.path.basename(file).split("_"):
		if "um" not in s :
			output_image += s + "_"
		else:
			output_image += (str(resolution) + "um_")
	output_image = output_image[:-1]
	output_image = os.path.join(os.path.dirname(file),output_image)

	at.inputs.reference_image = ref_image
	name = str.split(os.path.basename(output_image),'.nii')[0] + '_2dsurqec.nii.gz'
	#at.inputs.interpolation = 'NearestNeighbor' #TODO: Sure??
	at.inputs.interpolation = 'BSpline'
	output_image = os.path.join(os.path.dirname(output_image),name)
	at.inputs.output_image = output_image
	at.inputs.transforms = '/usr/share/mouse-brain-atlases/abi2dsurqec_Composite.h5'
	at.run()

	#TODO sform to qform
	return output_image

def download_annotation_file(path):
	anno_url_json = "http://api.brain-map.org/api/v2/structure_graph_download/1.json"
	anno_url_xml = "http://api.brain-map.org/api/v2/structure_graph_download/1.xml"
	filename_xml = "structure_graph.xml"
	filename_json = "structure_graph.json"

	if not os.path.isdir(path):os.mkdir(path)

	s = urllib.request.urlopen(anno_url_json)
	contents = s.read()
	file = open(os.path.join(path,filename_json), 'wb')
	file.write(contents)
	file.close()

	s = urllib.request.urlopen(anno_url_xml)
	contents = s.read()
	file = open(os.path.join(path,filename_xml), 'wb')
	file.write(contents)
	file.close()

def sort_and_archive(path="ABI-connectivity-dataHD"):
	arch = dict()
	arch_names_suff = dict()
	#TODO: There has to be an easier way...
	#TODO:check for any file that does not start with a letter
	arch[1] = glob.glob(os.path.join(path,"[Aa]*"))
	arch_names_suff[1] = "a"
	arch[2] = glob.glob(os.path.join(path,"[BbCc]*"))
	arch_names_suff[2] = "b-c"
	arch[3] = glob.glob(os.path.join(path,"[DdEe]*"))
	arch_names_suff[1] = "d-e"
	arch[4] = glob.glob(os.path.join(path,"[FfGgHhIiJj]*"))
	arch_names_suff[4] = "f-j"
	arch[5]= glob.glob(os.path.join(path,"[KkLl]*"))
	arch_names_suff[5] = "k-l"
	arch[6] = glob.glob(os.path.join(path,"[Mm]*"))
	arch_names_suff[6] = "m"
	arch[7] = glob.glob(os.path.join(path,"[NnOo]*"))
	arch_names_suff[7] = "n-o"
	p_list = sorted(glob.glob(os.path.join(path,"[Pp]*")))
	ind = [p_list.index(i) for i in p_list if 'Primary' in i][0]
	arch[8] = p_list[0:ind]
	arch_names_suff[8] = "pa-pre"
	arch[9]= p_list[ind:len(p_list)]
	arch_names_suff[9] = "pri-po"
	arch[10] = glob.glob(os.path.join(path,"[QqRR]*"))
	arch_names_suff[10] = "q-r"
	arch[11] = glob.glob(os.path.join(path,"[Ss]*"))
	arch_names_suff[1] = "a"
	arch[12] = glob.glob(os.path.join(path,"[TtUuVvWwXxYyZz]*"))
	arch_names_suff[12] = "t-z"
	number_of_archives = 12
	number_of_folders = len(os.listdir(path))

	for i in range(1,(number_of_archives+1)):
		folder_name= os.path.join(path,"ABI-connectivity-dataHD_" + arch[i] + "-0.1")
		if not os.path.isdir(folder_name):os.mkdir(folder_name)
		for file in arch[i]:
			new_path = os.path.join(folder_name,os.path.basename(file))
			os.rename(file,new_path)
		tarname=folder_name + ".tar.xz"
		create_archive(tarname,folder_name)


def create_archive(tarname,path):
	path = path
	tar_name = tarname
	print(path)
	print(tar_name)
	with tarfile.open(tar_name, "w:xz") as tar_handle:
		for root,dirs,files in os.walk(path):
			for file in files:
				tar_handle.add(os.path.join(root,file))

#TODO: Do I really need that? Usefule for expression data, but here?
def save_info(info,folder_name):
	path= os.path.join(folder_name,"ABI-connectivity-ids.csv")
	f = open(path,"w")
	for exp in info:
		f.write('\n')
		f.write(str(exp))

def main():
	#TODO: some sort of parallel download should be possible, stating totalrows and startrows differently for simultaneous download
	#TODO: timeout for urllib
	parser = argparse.ArgumentParser(description="Similarity",formatter_class=argparse.ArgumentDefaultsHelpFormatter)
	parser.add_argument('--package_name','-n',type=str,default="ABI-connectivity-data")
	parser.add_argument('--package_version','-v',type=str,default="9999")
	parser.add_argument('--startRow','-s',type=int,default=0)
	parser.add_argument('--numRows','-r',type=int,default=2000)
	parser.add_argument('--totalRows','-t',type=int,default=-1)
	parser.add_argument('--resolution','-x',type=int)
	args=parser.parse_args()

	folder_name = args.package_name + "-" + args.package_version
	download_annotation_file(folder_name)
	info=GetExpID(startRow=args.startRow,numRows=args.numRows,totalRows=args.totalRows)
	download_all_connectivity(info,folder_name=folder_name,resolution=args.resolution)
	#save_info(info)
	#create_archive()
	#sort_and_archive()


if __name__ == "__main__":
	main()
