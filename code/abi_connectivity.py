import argparse
import time
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
import glob
#import xmltodict
from datetime import datetime
from collections import defaultdict
from nipype.interfaces.ants import ApplyTransforms
from nipype.interfaces.ants.base import ANTSCommand, ANTSCommandInputSpec
from nipype.interfaces.base import BaseInterface, BaseInterfaceInputSpec, traits, File, Str, TraitedSpec, Directory, CommandLineInputSpec, CommandLine, InputMultiPath, isdefined, Bunch, OutputMultiPath
from pathlib import Path

API_SERVER = "http://api.brain-map.org/"
API_DATA_PATH = API_SERVER + "api/v2/data/"

def get_exp_id(
	startRow=0,
	numRows=2000,
	totalRows=-1,
	):
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
				info.append(x['id'])
		if totalRows < 0:
			totalRows = int(response['total_rows'])

		startRow += len(response['msg'])

		if startRow >= totalRows:
			done = True

	return info


def nrrd_to_nifti(file,
	target_dir=False,
	):
	print(f"Reading `{file}`.")
	readnrrd = nrrd.read(file)
	data = readnrrd[0]
	header = readnrrd[1]
	print(f"Converting `{file}`.")

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
	target_dir = os.path.abspath(os.path.expanduser(target_dir))
	os.makedirs(target_dir, exist_ok=True)
	nii_path = os.path.join(target_dir, os.path.basename(file).split(".")[0] + '.nii')
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


def get_sourcedata(info, dir_name,
	resolution=100,
	):
	"""
	Download all given genes corresponding to SectionDataSetID given in 100um and 25um resolution, converts nrrd to nii, registers to dsurqec... and resamples files to 40 and 200 respectively.

	Parameters:
	-----------
	SectionDataSetID : list(int)
		o=[0.200000002980232 0 0 -6.26999998092651; 0 0.200000002980232 0 -10.6000003814697; 0 0 0.200000002980232 -7.88000011444092; 0 0 0 1]list of SectionDataSetID to download.
	"""

	download_url = "http://api.brain-map.org/grid_data/download_file/"

	for exp in info:
		path_to_exp = os.path.join(dir_name,str(exp))
		#TODO: look inside if stuff is there...
		os.mkdir(path_to_exp)
		#TODO: so far no coordinate info. Also, avoid downloading twice
		path_to_metadata = get_exp_metadata(exp,path_to_exp)
		struc_name=get_identifying_structure(path_to_metadata)
		struc_name = struc_name.lower()
		struc_name= re.sub(" ","_",struc_name)
		struc_name=re.sub("[()]","",struc_name)
		new_name = struc_name + "-" + os.path.basename(path_to_exp)
		new_path = os.path.join(os.path.dirname(path_to_exp),new_name)
		os.rename(path_to_exp,new_path)
		resolution_url = "?image=projection_density&resolution=" + str(resolution)
		url = download_url + str(exp) + resolution_url
		# Trying higher timout to avoid spontaneous drop, unit is seconds
		# Last failed at:
		# http://api.brain-map.org/grid_data/download_file/165975096?image=projection_density&resolution=100
		fh = download_with_retry(url)
		filename = str.split((fh[1]._headers[6][1]),'filename=')[1] #TODO: Consistent??
		#TODO: do that differenttly ...
		filename = str.split(filename,";")[0]
		file_path_nrrd = os.path.join(new_path,filename)
		shutil.copy(fh[0],file_path_nrrd)
		os.remove(fh[0])

	return


def download_with_retry(url, max_retries=5, timeout=5):
	retries = 0
	print(f"Trying to download {url}.")
 
	while retries < max_retries:
		try:
			fh = urllib.request.urlretrieve(url)
			print(f"\t✔️ downloaded.")
			return fh
		#except urllib.error.URLError as e:
		except:
			#if isinstance(e.reason, TimeoutError):
			print(f"\ttimeout occurred, retrying ({retries + 1}/{max_retries})...")
			retries += 1
			time.sleep(timeout)  # Wait for a moment before retrying
			#else:
			#	raise
	print(f"\t❌download failed after {max_retries} retries.")


#def process_data(source_dir, data_dir, scratch_dir="~/.local/share/ABI-connectivity/", resolution=100,):
def process_data(source_dir, procdata_dir,
	resolution=100,
	):
	for nrrd_dir_name in os.listdir(source_dir):
		if os.path.isdir(os.path.join(source_dir,nrrd_dir_name)):
			nrrd_dir = os.path.join(source_dir,nrrd_dir_name)
			nrrd_data = glob.glob(os.path.join(nrrd_dir,"*.nrrd"))
			xml_data = glob.glob(os.path.join(nrrd_dir,"*.xml"))
			if len(nrrd_data) != 1:
				print(f"One NRRD data file expected in the `{nrrd_dir}` experiment directory, {len(nrrd_data)} found.")
				raise ValueError
			else:
				nrrd_data = nrrd_data[0]
			if len(xml_data) != 1:
				print(f"One XML metadata file expected the `{nrrd_dir}` in experiment directory, {len(xml_data)} found.")
				raise ValueError
			else:
				xml_data = xml_data[0]

			target_dir = os.path.join(procdata_dir, nrrd_dir_name)
			os.makedirs(target_dir, exist_ok=True)

			nii_data = nrrd_to_nifti(nrrd_data, target_dir)
			file_path_2dsurqec = apply_composite(nii_data, resolution=resolution)
			os.remove(nii_data)
			source_xml_path = xml_data
			target_xml_path = os.path.join(target_dir, os.path.basename(xml_data))
			shutil.copyfile(source_xml_path, target_xml_path)


def bids_rename(procdata_dir, bids_dir):
	for nii_dir in os.listdir(procdata_dir):
		if os.path.isdir(os.path.join(procdata_dir,nii_dir)):
			nii_dir = os.path.join(procdata_dir,nii_dir)
			nii_data = glob.glob(os.path.join(nii_dir,"*.nii.gz"))
			xml_data = glob.glob(os.path.join(nii_dir,"*.xml"))
			if len(nii_data) != 1:
				print(f"One NIfTI data file expected in the `{nii_dir}` experiment directory, {len(nii_data)} found.")
				raise ValueError
			else:
				nii_data = nii_data[0]
			if len(xml_data) != 1:
				print(f"One XML metadata file expected the `{nii_dir}` in experiment directory, {len(xml_data)} found.")
				raise ValueError
			else:
				xml_data = xml_data[0]

			# Extract metadata:
			metadata = {}
			tree = et.parse(xml_data)
			root = tree.getroot()
			# Maybe include an explicit list length check
			metadata['seed'] = {
				'acronym': root.findall('.//primary-injection-structure/acronym')[0].text,
				'safe name': root.findall('.//primary-injection-structure/safe-name')[0].text,
				'injection method': root.findall('.//stereotaxic-injection/injection-method')[0].text,
				'injection quality': root.findall('.//stereotaxic-injection/injection-quality')[0].text,
				}
			metadata['expression'] = {
				'name': root.findall('.//specimen/name')[0].text,
				}
			metadata['id'] = root.findall('.//id')[0].text
			# !!! Some files don't have Cre selectors listed, why?
			if not "Cre" in metadata['expression']['name']:
				continue
			m = re.match("(?P<expression_acronym>.+?)-(IRES-)?Cre.*",metadata['expression']['name'])
			if m:
				expression_acronym = m.groupdict()['expression_acronym'].replace("-", "")
				metadata['expression'] = {
					'acronym': expression_acronym,
					}
			else:
				continue

			# Create filenames.
			new_data_dir = os.path.join(
				bids_dir,
				f"seed-{metadata['seed']['acronym']}",
				)
			new_data_path = os.path.join(
				new_data_dir,
				f"seed-{metadata['seed']['acronym']}_expression-{metadata['expression']['acronym']}_FLUO.nii.gz"
				)
			new_path_dir = os.path.dirname(new_data_path)
			new_metadata_path = os.path.join(
				new_data_dir,
				f"seed-{metadata['seed']['acronym']}_expression-{metadata['expression']['acronym']}_FLUO.json"
				)

			# Write files.
			os.makedirs(new_path_dir, exist_ok=True)
			shutil.copyfile(nii_data, new_data_path)
			with open(new_metadata_path, 'w') as f:
				json.dump(metadata, f)


def download_all_connectivity(info,dir_name,resolution=[100,25]):
	"""
	Download all given genes corresponding to SectionDataSetID given in 100um and 25um resolution, converts nrrd to nii, registers to dsurqec... and resamples files to 40 and 200 respectively.

	Parameters:
	-----------
	SectionDataSetID : list(int)
		o=[0.200000002980232 0 0 -6.26999998092651; 0 0.200000002980232 0 -10.6000003814697; 0 0 0.200000002980232 -7.88000011444092; 0 0 0 1]list of SectionDataSetID to download.
	"""

	if resolution is None:
		resolution=[100,25]

	download_url = "http://api.brain-map.org/grid_data/download_file/"

	for resolution in res:
		if resolution == 100:
			path_to_res = dir_name
		if resolution <= 40:
			path_to_res = dir_name + "HD"
		if not os.path.isdir(path_to_res):
			os.mkdir(path_to_res)
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

		# Create archives:
		if resolution == 25:
			save_info(info,dir_name)
			tarname = dir_name + "HD" + ".tar.xz"
			create_archive(tarname, path_to_res)
		elif resolution == 100:
			save_info(info,dir_name)
			tarname = dir_name + ".tar.xz"
			create_archive(tarname, path_to_res)

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
		ref_image = '/usr/share/mouse-brain-templates/dsurqec_200micron_masked.nii'
		resolution = 200
	else:
		ref_image = '/usr/share/mouse-brain-templates/dsurqec_40micron_masked.nii'
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
	at.inputs.transforms = '/usr/share/mouse-brain-templates/abi2dsurqec_Composite.h5'
	at.run()

	#TODO sform to qform
	return output_image

def download_annotation_file(path):
	anno_url_json = "http://api.brain-map.org/api/v2/structure_graph_download/1.json"
	anno_url_xml = "http://api.brain-map.org/api/v2/structure_graph_download/1.xml"
	filename_xml = "structure_graph.xml"
	filename_json = "structure_graph.json"

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


def create_archive(tar_path, files_path):
	with tarfile.open(tar_path, "w:xz") as tar_handle:
		tar_handle.add(files_path, arcname=os.path.basename(files_path))


#TODO: Do I really need that? Useful for expression data, but here?
def save_info(info,dir_name):
	path= os.path.join(dir_name,"ABI-connectivity-ids.csv")
	f = open(path,"w")
	for exp in info:
		f.write('\n')
		f.write(str(exp))

def main():
	#TODO: some sort of parallel download should be possible, stating totalrows and startrows differently for simultaneous download
	parser = argparse.ArgumentParser(description="Similarity",formatter_class=argparse.ArgumentDefaultsHelpFormatter)
	parser.add_argument('--download-only', action='store_true', help='Only download source data.')
	parser.add_argument('--process-only', action='store_true', help='Only process already present source data.')
	parser.add_argument('--bids-only', action='store_true', help='Only reformat data to pseudo-BIDS.')
	parser.add_argument('--version','-v',type=str,default="9999")
	parser.add_argument('--startRow','-s',type=int,default=0)
	parser.add_argument('--numRows','-r',type=int,default=2000)
	parser.add_argument('--totalRows','-t',type=int,default=-1)
	parser.add_argument('--resolution','-x',type=int)
	args=parser.parse_args()

	now = datetime.today().strftime('%Y-%m-%dT%H:%M:%S')
	source_dir_name = os.path.join("sourcedata")
	procdata_dir_name = os.path.join("procdata")
	bids_dir_name = os.path.join("bids")
	Path(source_dir_name).mkdir(parents=True, exist_ok=True)
	download_annotation_file(source_dir_name)
	if (args.download_only and not args.process_only and not args.bids_only) or (not args.download_only and not args.process_only and not args.bids_only):
		info=get_exp_id(startRow=args.startRow,numRows=args.numRows,totalRows=args.totalRows)
		# In case there are any failures, the specific ID can be investigated by redefining `info` here.
		#print(info)
		#info = info[:3]
		#info = [157556400, 311845972]
		#print(info)
		get_sourcedata(info, dir_name=source_dir_name, resolution=args.resolution)
	if args.process_only and not args.download_only and not args.bids_only or (not args.download_only and not args.process_only and not args.bids_only):
		process_data(source_dir_name, procdata_dir=procdata_dir_name, resolution=args.resolution)
	if args.bids_only and not args.download_only and not args.process_only or (not args.download_only and not args.process_only and not args.bids_only):
		bids_rename(procdata_dir_name, bids_dir_name)


if __name__ == "__main__":
	main()
