import argparse
import copy
import json
import os
import sys
import urllib
import urllib.request
import shutil
import zipfile
import numpy
import nibabel
import re
import nrrd
from collections import defaultdict
from mhd_utils_3d import *
from nipype.interfaces.ants import ApplyTransforms
from nipype.interfaces.ants.base import ANTSCommand, ANTSCommandInputSpec
from nipype.interfaces.base import BaseInterface, BaseInterfaceInputSpec, traits, File, Str, TraitedSpec, Directory, CommandLineInputSpec, CommandLine, InputMultiPath, isdefined, Bunch, OutputMultiPath

#from nipype.interfaces.fsl import fslorient

API_SERVER = "http://api.brain-map.org/"
API_DATA_PATH = API_SERVER + "api/v2/data/"

#TODO: maybe merge into a single file that downloads either connectivtiy or gene expression data
#TODO: get some info on experiment data
def GetExpID():
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

    startRow = 0
    numRows = 1000
    totalRows = -1
    rows = []
    GeneNames = []
    SectionDataSetID = []
#    info = defaultdict(list)
    info = list()
#    GeneNames_cor = []
#    SectionDataSetID_cor = []

#    GeneNames_sag = []
#    SectionDataSetID_sag = []
    done = False

    while not done:
        #pagedUrl = API_DATA_PATH +"query.json?criteria=model::SectionDataSet,rma::criteria,products[abbreviation$eq'Mouse'],rma::include,specimen(stereotaxic_injections(primary_injection_structure,structures))startRow=%d&numRows=%d" % (startRow,numRows)
        r = "&start_row=%d&num_rows=%d" % (startRow,numRows)
        pagedUrl = API_DATA_PATH + "query.json?criteria=model::SectionDataSet,rma::criteria,products%5Bid$eq5%5D,rma::include,specimen(stereotaxic_injections(primary_injection_structure,structures))" + r
        print(pagedUrl)
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
    print("Converting " + file)

    affine_matrix = numpy.array(header["space directions"],dtype=numpy.float)
    affine_matrix = affine_matrix*0.001
    affine_matrix = numpy.insert(affine_matrix,3,[0,0,0], axis=1)
    affine_matrix = numpy.insert(affine_matrix,3,[0,0,0,1], axis=0)

    #Change Orientation from PIR to RAS. Steps: PIR -> RIP -> RPI -> RPS -> RAS
    data.setflags(write=1)
    data = numpy.swapaxes(data,0,2)
    data = numpy.swapaxes(data,1,2)
    data = data[:,:,::-1]
    data = data[:,::-1,:]
    data = data[::-1,:,:]  #TODO: Check for Atlas files!!!!!!
    img = nibabel.Nifti1Image(data,affine_matrix)
    nii_path = os.path.join(os.path.dirname(file), os.path.basename(file).split(".")[0] + '.nii')
    nibabel.save(img,nii_path)

    return nii_path
#TODO: separate python script?? Not needed after all...
class ResampleImageSpec(ANTSCommandInputSpec):
    dimension = traits.Enum(2,3,4,
            argstr='%d',
            position=1)

    input_image = File(
            argstr='%s',
            mandatory=True,
            position=2)

    output_image = File(
            argstr='%s',
            mandatory = True,
            position=3)
    
    M = traits.Str(
            argstr ='%s',
            mandatory = True,
            position=4)
    size = traits.Int(
            argstr = 'size=%d',
            position=5)

    spacing = traits.Int(
            argstr = 'spacing=%d',
            position=6)
    #TODO:interpolation= onyl necessary when size and spacing not declared, does it also work when they are declared
    interpolation = traits.Enum(0,1,2,3,4,
            argstr='interpolation=%d',
            position = 7)
    #TODO:optional parameters size, spacing, interpolation, blablabla...

def ants_int_resample(dim,input_image,resolution,interpolation,output_image = None):
    #print(str(dim),input_image,output_image,str(resolution),str(interpolation))
    ri = ResampleImage()
    ri.inputs.dimension = dim
    ri.inputs.input_image = input_image
    if output_image is None:
        #TODO: theres got to be an easier way...
        output_image = ""
        for s in input_image.split("_"):
            if "um" not in s :
                output_image += s + "_"
            else:
                output_image += (str(resolution) + "um_" + str(interpolation))
        output_image = output_image[:-1]
    print(output_image)
    ri.inputs.output_image = output_image
    resolution = resolution / float(1000)
    resolution_cmd = str(resolution) + 'x' + str(resolution) + 'x' + str(resolution)
    print(resolution_cmd)
    ri.inputs.M = resolution_cmd
    #ri.inputs.size = 1  TODO: Why did I take these out exactly? What do they do??
    #ri.inputs.spacing = 0
    ri.inputs.interpolation = interpolation
    print(ri.cmdline)
    ri.run()


class ResampleImageOutputSpec(TraitedSpec):
    output_image = File(exists=True,desc='Resampled Image')

class ResampleImage(ANTSCommand):
    _cmd = 'ResampleImage'
    input_spec = ResampleImageSpec
    output_spec = ResampleImageOutputSpec


def get_exp_metadata(exp,path):
    url_meta = API_DATA_PATH + "/SectionDataSet/query.xml?id=" + str(exp) + "&include=specimen(stereotaxic_injections(primary_injection_structure,structures))"
    filename = str(exp) + "_experiment_metadata.xml"
    s = urllib.request.urlopen(url_meta)
    contents = s.read()
    file = open(os.path.join(path,filename), 'wb')
    file.write(contents)
    file.close()

def download_all_connectivity(info):
    """
    Download all given genes corresponding to SectionDataSetID given in 100um and 25um resolution, converts nrrd to nii, registers to dsurqec... and resamples files to 40 and 200 respectively.

    Parameters:
    -----------
        SectionDataSetID : list(int)
            o=[0.200000002980232 0 0 -6.26999998092651; 0 0.200000002980232 0 -10.6000003814697; 0 0 0.200000002980232 -7.88000011444092; 0 0 0 1]list of SectionDataSetID to download.
    """
    if not os.path.isdir("/mnt/data/setinadata/abi_data/connectivity/ABI_connectivity_data"): os.mkdir("/mnt/data/setinadata/abi_data/connectivity/ABI_connectivity_data")
    download_url = "http://api.brain-map.org/grid_data/download_file/"
    for resolution in [100,25]:
        if resolution == 100: path_to_res = os.path.join("/mnt/data/setinadata/abi_data/connectivity/ABI_connectivity_data",("data_200um"))
        if resolution == 25: path_to_res = os.path.join("/mnt/data/setinadata/abi_data/connectivity/ABI_connectivity_data",("data_40um"))
        if not os.path.isdir(path_to_res):os.mkdir(path_to_res)
        for exp in info:
            #replace brackets with '_' and remove all other special characters
            path_to_exp = os.path.join(path_to_res,str(exp))
            print(path_to_exp)
            if os.path.isdir(path_to_exp):
                print("skip" + str(exp))
                continue
            os.mkdir(path_to_exp)
            get_exp_metadata(exp,path_to_exp) #TODO: so far no coordinate info. Also, avoid downloading twice 
            resolution_url = "?image=projection_density&resolution=" + str(resolution)
            url = download_url + str(exp) + resolution_url
            fh = urllib.request.urlretrieve(url)
            filename = str.split((fh[1]._headers[6][1]),'filename=')[1]  #TODO: Consistent??
            #TODO: do that differenttly ...
            filename = str.split(filename,";")[0]
            file_path_nrrd = os.path.join(path_to_exp,filename)
            print(file_path_nrrd)
            shutil.copy(fh[0],file_path_nrrd)
            os.remove(fh[0])
            #os.rename(fh[0],file_path_nrrd) only works if source and dest are on the same filesystem
            #file_path_res=ants_resampleImage(file_path,resolution)
            file_path_nii = nrrd_to_nifti(file_path_nrrd)
            print(file_path_nii)
            os.remove(file_path_nrrd)
            file_path_2dsurqec = apply_composite(file_path_nii,resolution)
            print(file_path_2dsurqec)
            os.remove(file_path_nii)
            #TODO: No need to resample if apply composite is already with a reference of target resolution. Check if we should get a composite-file at 25um!
            #if resolution == 25 :
            #    target_resolution = 40
            #elif resolution == 100:
            #    target_resolution = 200
            #print("to resample")
            #print(file_path)
            #ants_int_resample(3,file_path,target_resolution,0)
            #ants_int_resample(3,file_path,target_resolution,1)
            #ants_int_resample(3,file_path,target_resolution,2)
            #ants_int_resample(3,file_path,target_resolution,3)
            #ants_int_resample(3,file_path,target_resolution,4)
    
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
        ref_image = 'dsurqec_200micron_masked.nii'
        resolution = 200
    else:
        ref_image = 'dsurqec_40micron_masked.nii'
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
    at.inputs.transforms = 'abi2dsurqec_Composite.h5'
    at.run()

    #TODO sform to qform
    return output_image


def main():

    info=GetExpID()
    download_all_connectivity(info)


if __name__ == "__main__":
    main()
