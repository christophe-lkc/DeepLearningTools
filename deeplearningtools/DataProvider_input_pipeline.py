# ========================================
# FileName: DataProvider_input_pipeline.py
# Date: 29 june 2020 - 08:00
# Author: Alexandre Benoit plus some colleagues and interns such as Louis Klein on spring 2017
# Email: alexandre.benoit@univ-smb.fr
# GitHub: https://github.com/albenoit/DeepLearningTools
# Brief: A set of tools to preprocess data and build up input data pipelines
# for DeepLearningTools.
# =========================================
"""
  Warning:
    - These are advanced datapipelines => simpler versions are shown as tutorials is examples/data_pipelines
    - You may have to remove one of the cv2 or gdal import depending on your machine compatibility
"""
try:
  import cv2
except Exception as e:
  print('WARNING, could not load the opencv library, this will impact your data pipeline if willing to use it. Error report:',e)
try:
  from osgeo import gdal
except Exception as e:
  print('WARNING, could not load the GDAL library, this will impact your data pipeline if willing to use it. Error report:', e)

try:
  import rasterio
except Exception as e:
  print('WARNING, could not load the rasterio library, this will impact your data pipeline if willing to use it. Error report:', e)

import matplotlib.pyplot as plt
import glob
import os
import numpy as np
import copy
import tensorflow as tf
import unicodedata

dataprovider_namescope="data_input_pipeline"
filenames_separator='###'

def image_tfrecords_dataset(filename, hasLabels=False, dtype=tf.float32):
  """
  Assuming a set of tfrecords file is pointed by filename, ex:'images.tfrecords',
  create a data provider that loads them for training/testing models.

  :param filename: A path to the tfrecord files
  :type filename: str
  :type haslabel: A boolean, false by default that specifies if an iteger label is expected or not.

  :return: A tf.data.Dataset WITHOUT PREFETCH NOR BATCH, specify your own.
  """
  raw_image_dataset = tf.data.TFRecordDataset(filename)

  # Create a dictionary describing the features.
  image_feature_description = {
      'height': tf.io.FixedLenFeature([], tf.int64),
      'width': tf.io.FixedLenFeature([], tf.int64),
      'depth': tf.io.FixedLenFeature([], tf.int64),
      'image_raw': tf.io.VarLenFeature(dtype),
  }
  if hasLabels:
    image_feature_description.update({'label': tf.io.FixedLenFeature([], tf.int64)})

  def _parse_image_function(example_proto):
    # Parse the input tf.Example proto using the dictionary above.
    flat_sample=tf.io.parse_single_example(example_proto, image_feature_description)
    sample=tf.reshape(tf.sparse.to_dense(flat_sample['image_raw']), (flat_sample['height'], flat_sample['width'], flat_sample['depth']))
    return sample

  return raw_image_dataset.map(_parse_image_function)

def test_image_tfrecords_dataset(filename='test_dataset.tfrecords'):
  """  
  Suppose a dataset pointed by files 'test_dataset.tfrecords' exists, load it
  and display the recorded samples_saving_queuet.

  :param filename: A path to the tfrecord files.
  :type filename: str
  """
  #Read the created dataset
  dataset = image_tfrecords_dataset(filename)
  for sample in dataset:
    #print('sample shape', sample.shape)
    image_raw = sample.numpy()
    reference=None
    print('image_raw.shape[-1]',image_raw.shape[-1])
    if image_raw.shape[-1]==4:
      print('RGB image + reference channel')
      input_crop=image_raw[:,:,:3]
      reference=image_raw[:,:,3]
    elif image_raw.shape[-1]==3:
      print('Single RGB image ')
      input_crop=image_raw
    elif image_raw.shape[-1]==2:
      print('Gray image + reference channel')
      input_crop=image_raw[:,:,0]
      reference=image_raw[:,:,1]
    elif image_raw.shape[-1]==1 or len(image_raw.shape)==2:
      print('Single gray image')
      input_crop=image_raw
    else:
      raise ValueError('Failed to display array of shape '+str(image_raw.shape))

    #display relying on OpenCV
    sample_minVal=np.min(input_crop)
    sample_maxVal=np.max(input_crop)
    print('Sample value range (min, max)=({minVal}, {maxVal})'.format(minVal=sample_minVal, maxVal=sample_maxVal))
    input_crop_norm=(input_crop-sample_minVal)*255.0/(sample_maxVal-sample_minVal)
    cv2.imshow('TEST input crop rescaled (0-255)', cv2.cvtColor(input_crop_norm.astype(np.uint8), cv2.COLOR_RGB2BGR))
    if reference is None:
      cv2.imshow('TEST reference crop (classID*20)', reference.astype(np.uint8)*20)
    cv2.waitKey()

def make_images_coarse(input_images, downscale_factor=2):
    """
    Downscale and upscale a batch of images using nearest neighbors interpolation
    to make those images "coarse".

    :param input_images: The original images to make coarse (expecting 4D tensor)
    :type input_images: tf.Tensor
    :param downscale_factor: The downscaling factor to apply.
    :type downscale_factor: int

    :return: A batch of images of the same size as the input but made coarser spatially.
    """
    #downscale first
    init_height=input_images.get_shape().as_list()[1]
    init_width=input_images.get_shape().as_list()[2]
    new_height=init_height/downscale_factor
    new_width=init_width/downscale_factor
    downscaled=tf.image.resize_nearest_neighbor(
                                        input_images,
                                        size=[new_height, new_width],
                                        align_corners=True,
                                        name='reference_downscale'
                                    )
    #upscals back to initial resolution
    coarse_reference=tf.image.resize_nearest_neighbor(
                                        downscaled,
                                        size=[init_height, init_width],
                                        align_corners=True,
                                        name='reference_coarse'
                                    )

    return coarse_reference

def plot_sample_channel_histograms(data_sample, filenameID=''):
    """
    Basic data analysis.

    Plot the histogram of each channel of a data sample.

    :param data_sample: The numpy matrix to process.
    :type data_sample: np.array
    :param filenameID: The histogram filename prefix to be used.
    :type filenameID: str
    """
    for channelID in range(data_sample.shape[-1]):
        plt.figure('Channel ID='+str(channelID))
        plt.hist(data_sample[:,:,channelID])
        plt.title('Channel ID='+str(channelID))
        plt.savefig(str(filenameID)+'RS_dataset_sample_hist_channel'+str(channelID)+'.jpg')

def scaleImg_0_255(img):
    """
    Simply scale input values to range [0,255] to enable display using OpenCV.

    :param img: The numpy ndarray to rescale.
    :type img: np.array

    :return: the rescaled array, type remains the same.
    """
    #get the mask value
    print('Rescaling array of type:'+str(img.dtype))
    #copying before modifying
    img_copy=copy.deepcopy(img)
    try:
        maskValue=np.iinfo(img_copy.dtype).min
        #replace mask values by zeros
        img_copy[img_copy==maskValue]=0
    except Exception as e:
        print('Failed to detect data type, if float value, then, following should run fine. Error report:', e)
    img_min=np.nanmin(img_copy)
    img_max=np.nanmax(img_copy)
    epsilon=1e-4
    scaled_img=((img_copy-img_min)*255.0)/(img_max-img_min+epsilon)
    scaled_img[np.isnan(scaled_img)]=0
    return scaled_img

def debug_show_data(data, message):
    """
    Used for data debugging.

    :param data: The tensor to show.
    :type data: tf.Tensor
    :param message: A string to describe the debug message.

    Example usage:
      tf.py_function(debug_show_data, [raw_sample_crops, 'raw_sample crop'], tf.float32)
    """
    print("########################################################### DEBUG : {message}:shape={shape}, data={data}".format(message=message, shape=data.shape, data=data))
    return np.float32(1.0)

def extractFilenames(root_dir, file_extension="*.jpg", raiseOnEmpty=True):
    """
    Utility function which given a root directory and file extension, walk through folderfiles to
    create a list of searched files.

    :param root_dir: The root folder from which files should be searched.
    :type root_dir: str
    :param file_extension: The extension of the files.
    :type file_extension:
    :param raiseOnEmpty: A boolean, set True if an exception should be raised if no file is found
    """
    files  = []
    msg='extractFilenames: from working directory {wd}, looking for files {path} with extension {ext}'.format(wd=os.getcwd(),
                                                                                                                path=root_dir,
                                                                                                                ext=file_extension)
    print(msg)
    for root, dirnames, filenames in os.walk(root_dir):
        file_proto=os.path.join(root, file_extension)
        print('-> Parsing folder : '+file_proto)
        newfiles = glob.glob(file_proto)
        if len(newfiles)>0:
            print('----> Found files:'+str(len(newfiles)))
        files.extend(newfiles)

    if len(files)==0 and raiseOnEmpty is True:
        raise ValueError('No files found at '+msg)
    else:
        print('Found files : '+str(len(files)))
    return sorted(files)

def the_ugly_string_manager(filename):
  """
  Horribly ugly code to ensure that a filename string complies with gdal and opencv 
  when dealing with python 2 or 3 and pure python or tensorflow py_function.
  
  Convert to input to unicode to recover properly to string.

  FIXME : ... maybe just wait for the death of python2 and hope for a more elegant python3... but still waiting...
  """
  #tf.print('filename=',filename)
  #tf.print('dtype=', filename.dtype)
  if isinstance(filename, tf.Tensor):
      filename=filename.numpy()
  if not(isinstance(filename, bytes)):
      filename=bytes(filename, 'utf-8')
  filename_str=unicodedata.normalize('NFC', str(filename))
  if filename_str[0]=='b':
    filename_str=filename_str[2:-1]
  return filename_str

def imread_from_rasterio(filename, debug_mode=False):
  """
  Read an image using rasterio.
  
  Image is loaded as is. In case of a 3 channels image, a BGR to RGB conversion is applied.

  :param filename: A numpy array (coming from Tensorflow)
  :param debug_mode: Print more logs on this image read step
  """
  #get a valid filename string
  filename_str=the_ugly_string_manager(filename)

  with rasterio.open(filename_str, 'r') as ds:
    arr = ds.read()  # read all raster values

    if arr is None:
      raise ValueError('Could no read file {file}, exists={exists}'.format(file=filename_str,
                                                                           exists=os.path.exists(filename_str)
                                                                           )
                      )
  raster_array=arr.transpose([1,2,0])
  if debug_mode is True:
      print('Reading image with GDAL : {file}'.format(file=filename_str))
      print('Image shape='+str(raster_array.shape))
  img_array=raster_array.astype(np.float32)

  return img_array

def imread_from_gdal(filename, debug_mode=False):
  """
  Read an image using gdal.
  
  Image is loaded as is. In case of a 3 channels image, a BGR to RGB conversion is applied.

  :param filename: A numpy array (coming from Tensorflow)
  :param debug_mode: Print more logs on this image read step
  """
  #get a valid filename string
  filename_str=the_ugly_string_manager(filename)

  ds=gdal.Open(filename_str)
  if ds is None:
    raise ValueError('Could no read file {file}, exists={exists}'.format(file=filename_str,
                                                                         exists=os.path.exists(filename_str)
                                                                         )
                    )
  raster_array=ds.ReadAsArray().transpose([1,2,0])

  del ds #finally free memory...
  if debug_mode is True:
      print('Reading image with GDAL : {file}'.format(file=filename_str))
      print('Image shape='+str(raster_array.shape))
  img_array=raster_array.astype(np.float32)

  return img_array

def imread_from_opencv(filename, cv_imreadMode):
  """
  Read an image using opencv.
  
  Image is loaded as is. In case of a 3 channels image, a BGR to RGB conversion is applied.

  :param filename: A numpy array (coming from Tensorflow)
  :param debug_mode: Print more logs on this image read step
  :param cv_imreadMode: As described in the official opencv doc. Note: cv2.IMREAD_UNCHANGED=-1

  ISSUES : 

  https://github.com/tensorflow/tensorflow/issues/33400

  https://github.com/tensorflow/tensorflow/issues/27519
  """
  #get a valid filename string
  filename_str=the_ugly_string_manager(filename)
  #print("cv_imreadMode type is int", isinstance(cv_imreadMode, int))
  if not(isinstance(cv_imreadMode, int)):
    cv_imreadMode=cv_imreadMode.numpy()
  image=cv2.imread(filename_str, cv_imreadMode)
  if not(isinstance(image, np.ndarray)):
      raise ValueError('Could no read file {file}, exists={exists}'.format(file=filename_str,
                                                                           exists=os.path.exists(str(filename))
                                                                           )
                        )
  """if debug_mode == True:
      print('Image shape='+str(image.shape))
      if len(image.shape)>2:
          print('Image first layer min={minVal}, max={maxVal} (omitting nan values)'.format(minVal=np.nanmin(image[:,:,0]), maxVal=np.nanmax(image[:,:,0])))
      else:
          print('Image first layer min={minVal}, max={maxVal} (omitting nan values)'.format(minVal=np.nanmin(image), maxVal=np.nanmax(image)))
  """
  if len(image.shape)==3: ##reorder channels, from the loaded opencv BGR to tensorflow RGB use
    if image.shape[2]==3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
  return image

@tf.function
def normalised_entropy(counts):
  """
  Calculates the normalized entropy based on the counts of different classes.

  :param counts: A tensor representing the counts of each class.

  :return: entropy_normalized: The normalized entropy value.
  """
  classes_prob=tf.math.divide(tf.cast(counts, dtype=tf.float32), tf.cast(tf.reduce_sum(counts), dtype=tf.float32))
  #tf.print('classes_prob', [classes_prob], summarize=-1)
  entropy= -tf.reduce_sum(classes_prob*tf.math.log(classes_prob+0.001))
  entropy_normalized=tf.math.divide(entropy,tf.math.log(0.001+tf.cast(tf.math.count_nonzero(counts), dtype=tf.float32)))
  return entropy_normalized

@tf.function
def get_sample_entropy_int(sample):
  """
  Basic entropy computation relying on input sample histogram, making the hypothesis of a specific data range (here [0, 1000]).

  :return: The entropy of the input tensor.
  """
  with tf.name_scope('sample_entropy'):
      # get sample histogram, making the hypothesis of a specific values range
      counts=tf.histogram_fixed_width(tf.cast(sample, dtype=tf.int32), value_range=[0, 255], nbins=256, dtype=tf.int32)
      return normalised_entropy(counts)

@tf.function
def get_sample_entropy(sample):
  """
  Return the entropy of the input tensor.
  """
  with tf.name_scope('sample_entropy'):
      #count unique values occurences
      unique_values, values_idx, counts=tf.unique_with_counts(sample)
      #check if more than one class
      normalized_entropy=tf.cond(tf.greater(tf.shape(counts)[0], 1), lambda :normalised_entropy(counts), lambda :0.0)
      #normalized_entropy=tf.Print(normalized_entropy, [counts, normalized_entropy, tf.py_function(get_samples_entropies, [tf.expand_dims(sample,0)], tf.float32)], message='tf_entropyVShandmade')
      return normalized_entropy

def get_sample_entropy_test(values=[0,0,0,1,1,1]):
  """
  Test function of get_sample_entropy(sample) which entropy is being computed.

  :param values: Optionnal parameter to be filled with an array of values.
  """
  with tf.Session() as sess:
      data=tf.placeholder(dtype=tf.float32, shape=[None])
      entropy_val=sess.run(get_sample_entropy(data), feed_dict={data:values})
      print('Test data='+str(values)+' => Entropy value='+str(entropy_val))

def get_samples_entropies(samples_batch):
  """
  From a batch of 2D image labels, select a subset that ensures a minimum entropy.

  :param samples_batch: The batch of input data.
  :return: The vector of size (batchsize) with sample entropy values.
  """
  #print('input crops shape='+str(samples_batch.shape))
  nb_samples=samples_batch.shape[0]
  entropies=np.zeros(nb_samples, dtype=np.float32)
  flatten_samples=np.reshape(samples_batch, [nb_samples, -1]).astype(np.int)

  for it in range(nb_samples):
      #print('processing sample '+str(it))
      classes_id_count=np.unique(flatten_samples[it], return_counts=True)
      if len(classes_id_count[0])==1:
          continue
      #print('classes_id_count='+str(classes_id_count))
      classes_prob=classes_id_count[1].astype(float)/float(len(flatten_samples[it]))
      entropies[it]=-(classes_prob*np.log(classes_prob)).sum()/np.log(float(len(classes_prob)))
  return entropies

@tf.function(input_signature=[tf.TensorSpec(shape=[None, None, None], dtype=tf.int32)])
def convert_semanticMap_contourMap(crops):
  """
  Convert a semantic map into a contour Map using Sobel operator.

  :param crops: the semantic reference map to obtain contour (expecting 4D tensor).
  :type crops: tf.Tensor

	:return: An image batch containing contours of a semantic maps.
	"""
  #Border Sobel operator
  sobel_x = tf.constant([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], tf.int32)
  sobel_x_filter = tf.reshape(sobel_x, [3, 3, 1,1])
  sobel_y_filter = tf.transpose(sobel_x_filter, [1, 0, 2,3])


  image_resized = tf.expand_dims(crops, -1)

  print('processed crops:', image_resized)
  filtered_x = tf.nn.conv2d(image_resized, sobel_x_filter,
                        strides=[1, 1, 1, 1], padding='VALID')
  filtered_y = tf.nn.conv2d(image_resized, sobel_y_filter,
                        strides=[1, 1, 1, 1], padding='VALID')

  #sum and threshold
  contours_valid=tf.greater(tf.multiply(filtered_x,filtered_x)+tf.multiply(filtered_y,filtered_y), 1)

  #Add paddings to keep the same shape
  contours = tf.pad(contours_valid, paddings=[[0,0],[1,1],[1,1],[0,0]])

  return contours

class FileListProcessor_Semantic_Segmentation:

    dataprovider_namescope=dataprovider_namescope+'/FileListProcessor_Semantic_Segmentation'

    def _whiten_sample(self, sample):
      """
      Apply whitening to a raw+reference image tensorflow.

      If self.no_reference is False, then input is expected to be a single tensor which first layers are the raw data and the last layer is dense semantic reference
      raw data and reference data are first sliced, whitening is applied on ra data only and finally a single tensor
      is reconstructed and returned. If self.no_reference is True, then the input tensor if considered as a batch on raw data that is being standardized.
      
      :return: A tensor similar to the input but which raw data layers have been whitened.
      """
      with tf.name_scope('raw_data_whithening'):
          #apply whitening on the raw data only
          if self.no_reference is False:
              single_image_channels=tf.slice( sample,
                                              begin=[0,0,0],
                                              size=[-1,-1,self.single_image_raw_depth])
              reference_img=tf.slice( sample,
                                              begin=[0,0,self.single_image_raw_depth],
                                              size=[-1,-1,self.single_image_reference_depth])
              reference_img=tf.cast(reference_img, dtype=self.dtype)
              raw_sample=tf.image.per_image_standardization(single_image_channels)
              return tf.concat([tf.cast(raw_sample, dtype=self.dtype), reference_img], axis=2)
          else:
              return tf.image.per_image_standardization(single_image_channels)

    def _setup_load_raw_ref_images_from_separate_files(self):
      """
      Load one raw image and its related reference image and concatenate them into the same image
      images must be of the same size !

      TODO add asserts to heck matching sizes and expected depth

      :param raw_img_filename: The filename of the raw image to load.
      :param ref_img_filename: The filename of the reference image to load.
      :return: The concatenated image of same 2D size but of depth = raw.depth+ref.depth
      """
      if self.use_alternative_imread is not None:
        if self.use_alternative_imread == 'opencv':
          @tf.function
          def load_from_opencv(raw_ref_img_filenames):
            #first split filenames into two strings
            splitted_filenames = tf.strings.split(tf.expand_dims(raw_ref_img_filenames,0), sep=filenames_separator)
            print('splitted_filenames.values[0]=',splitted_filenames.values[0])
            raw_img_filename=splitted_filenames.values[0]
            ref_img_filename=splitted_filenames.values[1]
            # use Opencv image reading methods WARNING, take care of the channels order that may change !!!
            raw_image = tf.py_function(imread_from_opencv, [raw_img_filename, self.opencv_read_flags], tf.float32)
            reference_image = tf.py_function(imread_from_opencv, [ref_img_filename, cv2.IMREAD_GRAYSCALE], tf.float32)
            #add a third channel (to be compatible with raw_image rank when willing to concatenate
            raw_image=tf.cond(tf.rank(raw_image)==3, true_fn=lambda :raw_image, false_fn=lambda: tf.expand_dims(raw_image, -1))
            reference_image=tf.expand_dims(reference_image, -1)
            #concatenate both images in a single one
            return tf.concat([raw_image, reference_image], axis=2, name='concat_inputs')

          self.image_loading_fn=load_from_opencv
        

        elif self.use_alternative_imread == 'gdal':
          # use gdal image reading methods WARNING, take care of the channels order that may change !!!

          @tf.function
          def load_from_gdal(raw_ref_img_filenames):
            #first split filenames into two strings
            splitted_filenames = tf.strings.split(tf.expand_dims(raw_ref_img_filenames,0), sep=filenames_separator)
            print('splitted_filenames.values[0]=',splitted_filenames.values[0])
            raw_img_filename=splitted_filenames.values[0]
            ref_img_filename=splitted_filenames.values[1]
            raw_image = tf.py_function(imread_from_gdal, [raw_img_filename], tf.float32)
            reference_image = tf.py_function(imread_from_gdal,[ref_img_filename], tf.float32)
            #add a third channel (to be compatible with raw_image rank when willing to concatenate
            reference_image=tf.expand_dims(reference_image, -1)                      
            #concatenate both images in a single one
            return tf.concat([raw_image, reference_image], axis=2, name='concat_inputs')

          self.image_loading_fn=load_from_gdal
          
        
        elif self.use_alternative_imread == 'rasterio':
          # use gdal image reading methods WARNING, take care of the channels order that may change !!!

          @tf.function
          def load_from_rasterio(raw_ref_img_filenames):
            #first split filenames into two strings
            splitted_filenames = tf.strings.split(tf.expand_dims(raw_ref_img_filenames,0), sep=filenames_separator)
            print('splitted_filenames.values[0]=',splitted_filenames.values[0])
            raw_img_filename=splitted_filenames.values[0]
            ref_img_filename=splitted_filenames.values[1]
            raw_image = tf.py_function(imread_from_rasterio, [raw_img_filename], tf.float32)
            reference_image = tf.py_function(imread_from_rasterio, [ref_img_filename], tf.float32)
            #add a third channel (to be compatible with raw_image rank when willing to concatenate
            reference_image=tf.expand_dims(reference_image, -1)
            #concatenate both images in a single one
            return tf.concat([raw_image, reference_image], axis=2, name='concat_inputs')

          self.image_loading_fn=load_from_rasterio

      else:
          # use Tensorflow image reading methods
          @tf.function
          def load_from_tf(raw_ref_img_filenames):
            #first split filenames into two strings
            splitted_filenames = tf.strings.split(tf.expand_dims(raw_ref_img_filenames,0), sep=filenames_separator)
            #print('splitted_filenames.values[0]=',splitted_filenames.values[0])
            raw_img_filename=splitted_filenames.values[0]
            ref_img_filename=splitted_filenames.values[1]
            #-> read raw data
            single_raw_element = tf.io.read_file(raw_img_filename)
            single_reference_element = tf.io.read_file(ref_img_filename)
            #decode raw data using a specific decoder
            raw_image=tf.image.decode_png(single_raw_element, channels=self.single_image_raw_depth, dtype=None, name="single_image_raw_read")
            reference_image=tf.image.decode_png(single_reference_element, channels=self.single_image_reference_depth, dtype=None, name="single_image_reference_read")
            #concatenate both images in a single one
            return tf.concat([raw_image, reference_image], axis=2, name='concat_inputs')

          self.image_loading_fn=load_from_tf


      print('raw data channels='+str(self.single_image_raw_depth))
      print('dense semantic labels channels='+str(self.single_image_reference_depth))
            
    def _setup_load_raw_ref_images_from_single_file(self):
      """
      Load one raw image with its related reference image encoded as the last channel.

      :param raw_img_filename: The filename of the raw image to load with last channel being the reference semantic data.

      :return: The concatenated image of same 2D siae but of depth = raw.depth+ref.depth
      """
      if self.use_alternative_imread == 'opencv':
        # use Opencv image reading methodcropss WARNING, take care of the channels order that may change !!!
        @tf.function
        def load_from_opencv(raw_img_filename):
          return tf.py_function(imread_from_opencv, [raw_img_filename, self.opencv_read_flags], tf.float32)
        self.image_loading_fn=load_from_opencv
      
      elif self.use_alternative_imread == 'gdal':
        # use GDAL image reading methodcropss WARNING, take care of the channels order that may change !!!
        @tf.function
        def load_from_gdal(raw_img_filename):
          return tf.py_function(imread_from_gdal, [raw_img_filename], tf.float32)
        self.image_loading_fn=load_from_gdal
      elif self.use_alternative_imread == 'rasterio':
        # use rasterio image reading methodcropss WARNING, take care of the channels order that may change !!!
        @tf.function
        def load_from_rasterio(raw_img_filename):
          return tf.py_function(imread_from_rasterio, [raw_img_filename], tf.float32)
        self.image_loading_fn=load_from_rasterio
      else:
        raise ValueError('Neither OpenCV nor GDAL selected to read data and ground truth from the same image')
        
    def _generate_crops(self, sample_filename):
        """
        Considering an input tensor of any shape, divide it into overlapping windows and put them into a queue.
        
        Reference : inspired from http://stackoverflow.com/questions/40186583/tensorflow-slicing-a-tensor-into-overlapping-blocks

        :param input_image: Image to be sampled.
        """
        @tf.function
        def crops_dataset(image_filename):
          with tf.name_scope('generate_crops'):
              input_image=self.image_loading_fn(image_filename)
              with tf.name_scope('prepare_crops_bbox'):
                  height=tf.cast(tf.shape(input_image)[0], dtype=tf.int32, name='image_height')
                  width=tf.cast(tf.shape(input_image)[1], dtype=tf.int32, name='image_width')
                  #tf.print('height, width',im [height, width])
                  if self.shuffle_samples is True:
                      self.nbPatches=tf.cast(self.image_area_coverage_factor*tf.cast(height*width, dtype=tf.float32)/tf.constant(self.patchSize*self.patchSize, dtype=tf.float32), dtype=tf.int32, name='number_of_patches')
                      self.nbPatches=tf.minimum(self.nbPatches, tf.constant(self.max_patches_per_image, name='max_patches_per_image'), name='saturate_number_of_patches')
                      random_vector_shape = tf.expand_dims(self.nbPatches,0)
                      top_coord = tf.random.uniform(random_vector_shape,0, height-self.patchSize,dtype=tf.int32,name='patch_top_coord_top')
                      left_coord = tf.random.uniform(random_vector_shape,0,width-self.patchSize, dtype=tf.int32,name='patch_left_coord')
                  
                  else: #expecting TEST dataset use case : no padding, only processing original pixels, avoiding border effects
                      top_coord = tf.range(0, height-self.patchSize,self.patchSize-2*self.radius_of_view,dtype=tf.int32)
                      left_coord = tf.range(0,width-self.patchSize, self.patchSize-2*self.radius_of_view,dtype=tf.int32)

                      flat_meshgrid_y, flat_meshgrid_x = tf.meshgrid(top_coord, left_coord)
                      left_coord = tf.reshape(flat_meshgrid_x, [-1])
                      top_coord =  tf.reshape(flat_meshgrid_y, [-1])
                      self.nbPatches = tf.shape(left_coord)[0]

                  boxes_raw=tf.stack([top_coord, left_coord], axis=1)
                  
                  @tf.function
                  def get_crop(boxe):
                    crop=tf.image.crop_to_bounding_box(input_image, boxe[0], boxe[1], self.patchSize, self.patchSize)
                    return crop# cast will be done later...tf.cast(crop, self.dtype)
                  crops_bb=tf.data.Dataset.from_tensor_slices(boxes_raw)
                  crops=crops_bb.map(get_crop)#, num_parallel_calls=tf.data.AUTOTUNE, deterministic=not(self.shuffle_samples))
                  
                  # return the per image dataset BUT filter out unnecessary crops BEFORE
                  return crops.filter(self._crop_filter).prefetch(tf.data.AUTOTUNE)
        print("++++++++++++++++++++++++++++++++", sample_filename)
        return crops_dataset(sample_filename)

    def _setup_crop_filters(self):
      """
      Prepare a list of tf functions to be applied in order to filter out samples.
      """
      print('*************************** FILTERS ***************************')
      print(self.additionnal_filters)
      if self.balance_classes_distribution is True  and self.no_reference is False: #TODO second test is a safety test that could be removed is safety test done before
          print('-> crops filter: crops filtering taking into account ground truth entropy')
          @tf.function #(input_signature=[tf.TensorSpec(shape=[None, None, None], dtype=self.dtype)])
          def balance_classes_entropy(crop):
            ref_slice=tf.slice(crop,
                              begin=[0,0,self.single_image_raw_depth],
                              size=[-1,-1,self.single_image_reference_depth])
            return tf.greater(get_sample_entropy_int(tf.reshape(ref_slice,[-1])), self.classes_entropy_threshold, name='minimum_labels_entropy_selection')
          # add this filter as first in the filters list
          self.additionnal_filters.insert(0,balance_classes_entropy)

      if self.manage_nan_values == 'avoid':
          print('-> crops filter: crops with Nan values will be avoided')
          @tf.function #(input_signature=[tf.TensorSpec(shape=None, dtype=self.dtype)])
          def has_no_nans(crop):
            return tf.logical_not(tf.reduce_any(tf.math.is_nan(crop)))#tf.math.logical_and(selected_crops, tf.reduce_any(tf.is_nan(crop_candidate, axis=0)))
          # add this filter as first in the filters list
          self.additionnal_filters.insert(0,has_no_nans)
      #final counts
      self.nb_filters=len(self.additionnal_filters)

    def _crop_filter(self, crop):
      """
      A tf.data.Dataset filter function.
      
      :param crops: A set of crop candidates.
        
      :return selected_crops: A vector of size equal to the number of input crops with True for accepted candidates, False if not.
      """
      print('_crop_filter, input tensor=', crop)
    
      @tf.function
      def crop_filter(crop):
        with tf.name_scope('filter_crops'):
          #next processing wrt config
          
          """
          #run all filters as a cascade, one skip the remaining filters as long as one filter refuses the crop
          def run_filters_cond(filters, crop):
            #if no more filter should be applied, then the crop is accepted
            if len(filters)==0:
                return  tf.constant(True)
            print('--> applying filter:',filters[0])
            # if current filter rejects the crop, then return stop, else, aply next filter
            return tf.cond(filters[0](crop), lambda: run_filters_cond(filters[1:], crop), lambda:tf.constant(False))
          print('Processing crop filter list :',self.additionnal_filters)
          selected_crop=run_filters_cond(self.additionnal_filters, crop)
          
          filter_ok=tf.constant(True)
          filter_id=tf.constant(1)
          c = lambda filter_id, filter_ok:filter_ok
          b = lambda filter_id, filter_ok: (tf.add(filter_id, 1), tf.math.logical_and(filter_ok, self.additionnal_filters[filter_id](crop)))
          filter_id, filter_ok = tf.while_loop(c, b, [filter_id, filter_ok])
          return filter_ok

          """
          filter_ok=True
          for i in range(self.nb_filters):
            filter_ok&= self.additionnal_filters[i](crop)
          return filter_ok
          """
          #selected_crop=tf.Print(selected_crop, [selected_crop], message=('Crop is selected'))
          return selected_crop
          """
      return crop_filter(crop)

    def _setup_image_transforms(self):
      """
      Prepare a list of tf functions to be applied along the data pipeline.
      """
      #prepare a random number generator that will act on the random image transforms
      self.rng = tf.random.Generator.from_seed(self.seed, alg='philox')

      self.image_label_transforms=[]
      print('*************************** Image transforms ***************************')

      #apply basic transforms to both image data AND associated metadata (labels and so on)
      if self.manage_nan_values == 'zeros':
          print('-> nan replacement by zeros')
          @tf.function
          def replace_nans_by_zeros(sample, seed):
            """ returns a tensor with input nan values replaced by zeros """
            return tf.where(tf.math.is_nan(sample), tf.zeros_like(sample), sample)
          self.image_label_transforms.append(replace_nans_by_zeros)
      if self.apply_random_flip_left_right:
          print('-> random flipping left right')
          self.image_label_transforms.append(tf.image.stateless_random_flip_left_right)
      if self.apply_random_flip_up_down:
          print('-> random flipping up down')
          self.image_label_transforms.append(tf.image.stateless_random_flip_up_down)
      if self.apply_random_rot90:
          print('-> random random 90deg rotation')
          @tf.function
          def random_rot90(img, seed):
            return tf.image.rot90(img, tf.random.uniform(shape=[], minval=0, maxval=4, dtype=tf.int32))
          self.image_label_transforms.append(random_rot90)

      self.image_pixels_transforms=[]
      if self.no_reference is False: #if using a reference channel, then apply transform only of the raw data
          @tf.function
          def get_image_channels(img, seed):
            return tf.slice( img,
                                          begin=[0,0,0],
                                          size=[-1,-1,self.single_image_raw_depth])
          self.image_pixels_transforms.append(get_image_channels)


      if self.apply_whitening:     # Subtract off the mean and divide by the variance of the pixels.
          print('-> image standardization')
          @tf.function
          def img_standardize(img, seed):
            return tf.image.per_image_standardization(img)
          self.image_pixels_transforms.append(img_standardize)
          
      if self.apply_random_brightness is not None:
          print('-> random brightness, max_delta=', self.apply_random_brightness)
          @tf.function
          def apply_random_brightness(img, seed):
            return tf.image.stateless_random_brightness(img, max_delta=self.apply_random_brightness, seed=seed)
          self.image_pixels_transforms.append(apply_random_brightness)

      if self.apply_random_saturation is not None:
          low=1.0-self.apply_random_saturation
          high=1.0+self.apply_random_saturation
          print('-> random saturation (lower, upper)=', (low, high))
          @tf.function
          def apply_random_saturation(img, seed):
            return tf.image.stateless_random_saturation(img, lower=low, upper=high, seed=seed)
          self.image_pixels_transforms.append(apply_random_saturation)
      
      if self.apply_random_contrast is not None:
          low=1.0-self.apply_random_contrast
          high=1.0+self.apply_random_contrast
          print('-> random contrast (lower, upper)=', (low, high))
          @tf.function
          def apply_random_contrast(img, seed):
            return tf.image.stateless_random_contrast(img, lower=low, upper=high, seed=seed)
          self.image_pixels_transforms.append(apply_random_contrast)
      
      if self.crops_postprocess is not None:
          print('-> userdefined post process')
          self.post_process_fn=self.crops_postprocess
      else:
          @tf.function
          def no_op(crop, seed):
              return tf.identity(crop)
          self.post_process_fn=no_op

      #final counts:
      self.nb_global_transforms=len(self.image_label_transforms)
      self.nb_data_transforms=len(self.image_pixels_transforms)

    def _image_transform(self, input_image):
      """
      Apply a set of transformation to an input image.

      :param input_image: The image to be transformed. It must be a stack of
      the raw image (first layers) followed by the reference layer(s).

      :return: The transformed raw+reference concatenated image, only geometric transforms are applied to the reference image.
      """
      print('_image_transform, input tensor=', input_image)

      @tf.function
      def image_transform(input_image):
        with tf.name_scope('image_transform'):
          seed = self.rng.make_seeds(2)[0]

          print('Image_transform input: '+str(input_image))

          #retreive a single crop
          """ standard cropping scheme """
          transformed_image=input_image
          for i in range(self.nb_global_transforms):
            #print('-> Datapipeline applyies global image transform:', transform)
            transformed_image=self.image_label_transforms[i](transformed_image, seed)
          
          if self.no_reference is False: #if using a reference channel, then apply transform only of the raw data
            reference_img=tf.slice( transformed_image,
                                      begin=[0,0,self.single_image_raw_depth],
                                      size=[-1,-1,self.single_image_reference_depth])
            reference_img=tf.cast(reference_img, dtype=self.dtype)

          for i in range(self.nb_data_transforms):
            #print('-> Datapipeline applyies image data transform:', transform)
            transformed_image=self.image_pixels_transforms[i](transformed_image, seed)

          
          if self.no_reference is False:#get back to the input+reference images concat
            transformed_image= tf.concat([tf.cast(transformed_image, dtype=self.dtype), reference_img], axis=2)
          
          transformed_image= self.post_process_fn(transformed_image, seed)
          print('transformed_image', transformed_image)
          return transformed_image

      return image_transform(input_image)

    def _create_dataset_filenames(self):
      """
      Given the chosen mode (using a list of filename pairs of raw+ref image or using a single filename poiting a single raw+ref(lastchannel) image).
      
      :return: Create the filenames dataset.
      """
      if self.image_pairs_raw_ref_input:
          datasetFiles=[''+string1+filenames_separator+string2  for string1,string2 in zip(self.filelist_raw_data, self.filelist_reference_data)]
      else: #raw and ref data in the same image of only raw data use cases
          datasetFiles=self.filelist_raw_data
      #print(datasetFiles)

      #apply general setup for dataset reader : read all the input list one time, shuffle if required to, read one by one
      self.dataset=tf.data.Dataset.from_tensor_slices(datasetFiles).repeat(self.nbEpoch)
      if self.shuffle_samples:
            self.dataset=self.dataset.shuffle(len(datasetFiles))

    def _setup_load_raw_images_from_filenames(self):
      """
      Function to be applied for each of the dataset sample.
      
      This method prepares a tf.function refered to as self.image_loading_fn

      :param filenames: a single or tuple of filename(s) related to a given sample0
      """
      if self.image_pairs_raw_ref_input:
        self._setup_load_raw_ref_images_from_separate_files()
      else: #raw and ref data in the same image of only raw data use cases
        self._setup_load_raw_ref_images_from_single_file()

    def _create_data_pipeline(self):
      """ 
      Input pipeline is defined on the CPU parameters.
      """
      with tf.name_scope(FileListProcessor_Semantic_Segmentation.dataprovider_namescope+'_gen_crops_then_transform'):
          """create a first "queue" (actually a list) of pairs of image filenames
          and generate data samples (whole read images)
          """
          #1. let the dataset load the raw images and associates possible metadata as last channel(s)
          self._create_dataset_filenames()


          #2. transform the dataset samples convert raw images into crops
          if self.full_frame_mode is True:
            self.dataset=self.dataset.map(map_func=self._load_raw_images_from_filenames, num_parallel_calls=self.num_reader_threads).prefetch(1)
            with tf.name_scope('full_raw_frame_prefetching'):
              if self.apply_whitening:     # Subtract off the mean and divide by the variance of the pixels.
                  self.dataset=self.dataset.map(self._whiten_sample)
          else:
              self.dataset=self.dataset.interleave(cycle_length=self.num_reader_threads, block_length=1, map_func=self._generate_crops, num_parallel_calls=self.num_reader_threads, deterministic=not(self.shuffle_samples))

          self.dataset=self.dataset.map(self._image_transform, num_parallel_calls=tf.data.AUTOTUNE, deterministic=not(self.shuffle_samples))
          #finalise the dataset pipeline : filterout
          #finalize dataset (set nb epoch and batch size and prefetch)
          self.dataset=self.dataset.batch(self.batch_size, drop_remainder=True)#, num_parallel_calls=tf.data.AUTOTUNE, deterministic=not(self.shuffle_samples))
          self.dataset=self.dataset.prefetch(tf.data.AUTOTUNE)#int(self.batch_size*20))
          print('Input data pipeline graph is now defined')

    """
    @brief a class enabling couples of raw Data+ full frame reference samples enqueing
    *special case: if patch_ratio_vs_input==1 and max_patches_per_image==1
    -> then, enqueue the full image with full reference
    *when generating patches, the number of patches is computed like this:
    nbPatches_per_image=min(max_patches_per_image, image_area_coverage_factor*(input image pixels/(patchSize*patchSize))
      last member shows we initially get the optimal number of patches so that the number of pixels of eall the patches is similar to the input image number of pixels
      and this number of patches is multiplied by a factor given by the user. Upper limit is given by max_patches_per_image.
    ==> adjust max_patches_per_image and image_area_coverage_factor to your needs.
      Be aware that max_patches_per_image modulates the size of the samples queue so that large values gives large queues that ensures a good mixing of samples from various images
      Be aware that once all samples are generated for a given image, if balance_classes_distribution is True, then many samples are filtered out to ensure a good entropy level on the labels reference samples

    Parameters:
    filelist_raw_data: the list of raw files to process
    filelist_reference_data: reference data source follwing rule:
            -if provided data is a python list : this will be considered as the list of ground truth associated to the filelist_raw_data (SAME ORDER EXPECTED!)
            -if None, then the reference image is expected to be the last channel of the raw data
            -if -1, then, no reference is expected so that the data provider will only sample raw data and won't provide any reference data (as for unsupervised learning)
    nbEpoch: an integer that specifies the number of expected epoch (-1 or None forces to repeat indefinitely)
    shuffle_samples: set True if samples should be shuffled at the entry of the deep net (typical training use case),
                      set False to preserve patchs ordering on a regular grid NOTE : no zero padding is done, image right/bottom borders may not be sampled
    patch_ratio_vs_input: the size ratio of the crops generated from each input image
                --> if >=1 || <0, then, max_patches_per_image will be forced to 1
    max_patches_per_image: the number of crops extracted per image
    image_area_coverage_factor: the number of patches per images is automatically computed to get nearly the same number
      of pixels as the input image (surface coverage), this factor is applied
      to this number of patches. However the maximum limit of patches is forced by max_patches_per_image
    num_reader_threads: the number of parallel image readers used to generate input data
    apply_random_flip_left_right: set True if input should be randomly mirrored left-right,
    apply_random_flip_up_down: set True if input should be randomly mirrored up-down
    apply_random_rot90: set True to apply random 90 deg rotations
    apply_random_brightness: set None is not used, set >0 if brighness should be randomly adjusted by this factor
    apply_random_saturation: set None is not used, set >0 if saturation should be randomly adjusted by this factor
    apply_random_contrast: set None is not used, set >0 if contrast should be randomly adjusted by this factor
    apply_whitening: set True to whiten RAW DATA ONLY !!!
    batch_size: set the number of sample provided at each consuming step
    use_alternative_imread: set False if data should be loaded from tensorflow image read methods (for now, jpeg and png only)
    balance_classes_distribution: set False if no sample pop out should be applied
            set True if some sample crops should be removed in order to get equally distributed classes
    classes_entropy_threshold: if balance_classes_distribution is True, then use this parameter in range [0,1]
    in order to select crops with higher normalized entropy than this value
    opencv_read_flags: if usig OpenCV to read images, set here the specific cv2.ilread flags for specific image formats
    field_of_view: size of the field of view of a pixel. Used to define the size of the overlap of adjacent crops of an image when not using random crops
    manage_nan_values: set 'zeros' to replace nan values by zeros, 'avoid' to avoid sample crops with nan values, None else and Exception will be raised to highlight potential dataset problems
    additionnal_filters: must be a list of functions (empty by default) that take 1 parameter, a tensor that represents an image crop with eventual ground truth as additionnal layers and that return True if crop is of interest, else False
    crops_postprocess: a function (or None) that postprocesses the crops (can for example separate raw data and reference while cropping the latter or something else)
    dtype: the pixel data type to be used (default is tf.float32, more memory efficient format should be tf.float16)
    """

    def __init__(self, filelist_raw_data,
                    filelist_reference_data,
                    nbEpoch=-1,
                    shuffle_samples=True,
                    patch_ratio_vs_input=0.2,
                    max_patches_per_image=10,
                    image_area_coverage_factor=2.0,
                    num_reader_threads=4,
                    apply_random_flip_left_right=True,
                    apply_random_flip_up_down=False,
                    apply_random_rot90=False,
                    apply_random_brightness=0.5,
                    apply_random_saturation=0.5,
                    apply_random_contrast=0.5,
                    apply_whitening=True,
                    batch_size=50,
                    use_alternative_imread=False,
                    balance_classes_distribution=False,
                    classes_entropy_threshold=0.6,
                    opencv_read_flags=-1,#cv2.IMREAD_UNCHANGED=-1, #cv2.IMREAD_LOAD_GDAL | cv2.IMREAD_ANYDEPTH ):
                    field_of_view=0,
                    manage_nan_values=None,
                    additionnal_filters=None,
                    crops_postprocess=None,
                    dtype=tf.float16,
                    seed=42,
                    debug=False):
      self.filelist_raw_data=filelist_raw_data
      self.filelist_reference_data=filelist_reference_data
      self.nbEpoch=nbEpoch
      self.shuffle_samples=shuffle_samples
      self.patch_ratio_vs_input=patch_ratio_vs_input
      self.max_patches_per_image=max_patches_per_image
      self.image_area_coverage_factor=float(image_area_coverage_factor)
      self.num_reader_threads=num_reader_threads
      self.apply_random_flip_left_right=apply_random_flip_left_right
      self.apply_random_flip_up_down=apply_random_flip_up_down
      self.apply_random_rot90=apply_random_rot90
      self.apply_random_brightness=apply_random_brightness
      self.apply_random_saturation=apply_random_saturation
      self.apply_random_contrast=apply_random_contrast
      self.apply_whitening=apply_whitening
      self.batch_size=batch_size
      self.use_alternative_imread=use_alternative_imread
      self.balance_classes_distribution=balance_classes_distribution
      self.classes_entropy_threshold=classes_entropy_threshold
      self.opencv_read_flags=opencv_read_flags
      self.field_of_view = field_of_view
      self.manage_nan_values=manage_nan_values
      self.crops_postprocess=crops_postprocess
      self.dtype=dtype
      self.seed=seed
      self.debug = debug
      if additionnal_filters is None:
        self.additionnal_filters=[]
      else:
        self.additionnal_filters=additionnal_filters

      if self.image_area_coverage_factor<=0:
        raise ValueError('Error when constructing DataProvider: image_area_coverage_factor must be above 0')

      if not(isinstance(self.additionnal_filters, list)):
        raise ValueError('Error when constructing DataProvider: additionnal_filters must be a list of functions that take 1 parameter, a tensor that represents a crop with eventual ground truth as additionnal layers and return True if crop is of interest, else False')

      #first read the first raw and reference images to get aspect ratio and depth
      #FIXME : fast change to introduce gdal image loading, TO BE CLARIFIED ASAP !!!
      if self.use_alternative_imread == 'gdal':
        raw0=imread_from_gdal(filelist_raw_data[0], True)
      elif self.use_alternative_imread == 'rasterio':
        raw0=imread_from_rasterio(filelist_raw_data[0], True)
      else:
        raw0=imread_from_opencv(filelist_raw_data[0],opencv_read_flags)
      print('Read first raw image {filepath} of shape {shape}'.format(filepath=filelist_raw_data[0], shape=raw0.shape))
      self.single_image_raw_width = raw0.shape[0]
      self.single_image_raw_height = raw0.shape[1]

      #adjusting setup and pipeline architecture design depending on the inputs
      self.image_pairs_raw_ref_input=False
      self.no_reference=False
      if filelist_reference_data is None:
          #-> case of raw images that include reference as the last channel
          print('*** Dataprovider is sampling raw data and expects it to have reference (ground truth) at the last channel')
          self.single_image_raw_depth=raw0.shape[2]-1
          self.single_image_reference_depth=1
          self.fullframe_ref_shape=list(raw0.shape)
      elif isinstance(filelist_reference_data, list):
          print('*** Dataprovider is sampling raw data and reference data lists')
          self.image_pairs_raw_ref_input=True
          #-> case of raw images plus separate reference images
          ref0=cv2.imread(filelist_reference_data[0],self.opencv_read_flags)
          print('read first reference image {filepath} of shape {shape}'.format(filepath=filelist_reference_data[0], shape=ref0.shape))
          if (raw0.shape[0] != ref0.shape[0]) or (raw0.shape[1] != ref0.shape[1]):
              raise ValueError('FileListProcessor_input::__init__ Error, first input files do not have the same pixel size')
          if len(raw0.shape)>2:
              self.single_image_raw_depth=raw0.shape[2]
          elif len(raw0.shape)==2:
              self.single_image_raw_depth=1
          else:
              raise ValueError('input image shape not supported:'+str(raw0.shape))
          self.single_image_reference_depth=1
          self.fullframe_ref_shape=list(raw0.shape)
          self.fullframe_ref_shape[-1]=self.single_image_raw_depth+self.single_image_reference_depth

          if len(ref0.shape)>2:
              self.single_image_reference_depth=ref0.shape[2]
      else:
          print('*** Dataprovider is sampling raw data but not providing any reference data')
          self.no_reference=True
          self.single_image_raw_depth=raw0.shape[2]
          self.single_image_reference_depth=0
      self.img_ratio=float(raw0.shape[0])/float(raw0.shape[1])

      print('raw data channels='+str(self.single_image_raw_depth))
      print('dense semantic labels channels='+str(self.single_image_reference_depth))
          
      if self.field_of_view > 0:
        self.radius_of_view = (self.field_of_view-1)//2
      else:
        self.radius_of_view=0

      #parameters check:
      if patch_ratio_vs_input==1 or patch_ratio_vs_input<0:
          print('Each image will be entirely processed')
          self.patch_ratio_vs_input=1
          self.max_patches_per_image=1

      if patch_ratio_vs_input >1:
          self.patchSize=patch_ratio_vs_input
          self.patch_ratio_vs_input=float(patch_ratio_vs_input)/float(raw0.shape[0])
      else:
          self.patchSize=int(raw0.shape[0]*patch_ratio_vs_input)

      self.full_frame_mode=self.patch_ratio_vs_input==self.max_patches_per_image==1
      if self.full_frame_mode is True:
          print('==> each image will finally be processed globally following')
      else:
          print("Image patches will be of size:"+str(self.patchSize))
          print("Image patches ratio vs input is:"+str(self.patch_ratio_vs_input))

      # checking if field_of_view is odd
      if self.field_of_view%2 == 0 and self.field_of_view != 0:
          raise ValueError('field_of_view must be odd or 0 (current : {})'.format(self.field_of_view))

      #prepare the set of image transorms
      if self.full_frame_mode is True:
        self.cropSize=self.fullframe_ref_shape
      else:
        self.cropSize=[self.patchSize,self.patchSize,self.single_image_raw_depth+self.single_image_reference_depth]
      print('Deep net will be fed by samples of shape='+str(self.cropSize))
      self._setup_load_raw_images_from_filenames()
      self._setup_image_transforms()
      self._setup_crop_filters()
      #create the input pipeline
      self._create_data_pipeline()

    def get_config(self):
        return {'Datapipeline_cfg':None}

def extract_feature_columns(data_dict, features_labels):
  """
  Function that creates feature columns interpreters and applies them on
  the input data to prepare a dense tensor that will feed a model.

  :param data_dict: A batch of samples where columns are aggregated into a dictionary.
  :param features_labels: A dictionary following architecture:
    features_labels={'all_cols':{'names':colnames, 'record_defaults':record_defaults},
                    'data_cols':{'names_opt_categories_or_buckets':data_cols, 'indexes':data_idx},
                    'labels_cols':{'names':label_cols,'indexes':label_idx}}
    where names_opt_categories_or_buckets is a dictionnary that contains at
    least key 'name' and has an optionnal LIST specified by key :
      'vocabulary_list' if column is categorial and should be one hot encoded according to the specified vocabulary
      'buckets_boundaries' if column numeric but should be should be one hot encoded according to the specified boundarie values
      'normalizer_fn' if the column is numeric and should be normalized

  :return: a dense data tensor.
  """
  #preparing input data features, convert to the appropriate type
  data_features=[]
  for data_col in features_labels['data_cols']['names_opt_categories_or_buckets']:
      print('***preparing input data column:'+str(data_col))
      if len(data_col)==1 or 'normalizer_fn' in data_col:
        print('----->numeric data to be casted as float 32')
        normalization_fn=None
        if 'normalizer_fn' in data_col:
          normalization_fn=data_col['normalizer_fn']
          print('Normalization function found:'+str(data_col['normalizer_fn']))
        data_features.append(tf.feature_column.numeric_column(key=data_col['name'], normalizer_fn=normalization_fn))
      elif 'vocabulary_list' in data_col:
        print('----->categorial data to be one hot encoded')
        #name=data_col['name'].split(' ')[0]+'_indicator'
        data_features.append(tf.feature_column.indicator_column(tf.feature_column.categorical_column_with_vocabulary_list(
                    key=data_col['name'],
                    vocabulary_list=data_col['vocabulary_list'],
                    num_oov_buckets=1#allow one other category for value out of the vocabulary
                    )))
      elif 'buckets_boundaries' in data_col:
        print('----->numeric data to be one hot encoded with respect to some boundaries')
        # First, convert the raw input to a numeric column.
        numeric_feature_column = tf.feature_column.numeric_column(key=data_col['name'])
        # Then, bucketize the numeric column on the years 1960, 1980, and 2000.
        data_features.append(tf.feature_column.bucketized_column(source_column = numeric_feature_column, boundaries = data_col['buckets_boundaries']))
      else:
        raise ValueError('Could not manage the proposed data col')

  print('*** data columns, len='+str(len(data_dict))+' : '+str(data_dict))
  print('*** feature columns, len='+str(len(data_features))+' : '+str(data_features))
  data_vectors = tf.feature_column.input_layer(features=data_dict, feature_columns=data_features)
  print('*** data_vectors='+str(data_vectors))

  return data_vectors

def FileListProcessor_csv_time_series(files,
                                      csv_field_delim,
                                      record_defaults_values,
                                      batch_size,
                                      epochs,
                                      temporal_series_length,
                                      windowing_shift,
                                      na_value_string='N/A',
                                      labels_cols_nb=1,
                                      per_sample_preprocess_fn=None,
                                      selected_cols=None,
                                      shuffle=False,
                                      post_proc_filter=None):
  """
  A standard data pipeline dedicated to time series stored in collections of csv files.

  :param files: A python list of filenames.
  :param csv_field_delim: The column separator.
  :param record_defaults_values: A python list of default values to be used when csv columns are empty (ex for a 2 columns float table: [[0.0], 0.0]]).
  :param batch_size: Number of samples to be considered in a data batch.
  :param epochs: The number of epoch the dataset should be read.
  :param temporal_series_length: The number of successive lines to be read as a sequence of timesteps for a single sample.
  :param windowing_shift: The minimal temporal window/number of time steps that separate two overlapping samples.
  :param na_value_string='N/A': The string used in the csv file that indicated nan values.
  :param labels_cols_nb: The number of FIRST columns that represent labels (may be string dates or so).
  :param per_sample_preprocess_fn: If some specific sample level processing should be performed, privide here the function that does this (def mypost_proc(Tensor sample) returns Tensor).
  :param selected_cols: The python list of indexes of data columns of interest.
  :param shuffle=False: Set True to activate samples shuffling (best for training).
  :param post_proc_filter: If some specific sample filtering should be performed, specify here a dedicated function (def mypost_proc(Tensor sample) returns Binary Tensor).
  """

  @tf.function
  def decode_csv(line):
    features = tf.io.decode_csv(line, record_defaults=record_defaults_values, field_delim=csv_field_delim, na_value=na_value_string, select_cols=selected_cols)
    labels = tf.stack(features[:labels_cols_nb], axis=0)
    raw_data= tf.stack(features[labels_cols_nb:], axis=0)
    if per_sample_preprocess_fn is not None:
        #tf.print('CSV DECODE', raw_data, labels)
        return per_sample_preprocess_fn(raw_data, labels)
    return raw_data, labels
  #create a dataset from the list of files to process
  files_dataset=tf.data.Dataset.list_files(files).repeat(epochs)
  #a thread processes each file and each one is read by line blocks of length 'temporal_series_length'
  
  #read file lines in a sliding window fashion
  datasets = files_dataset.flat_map(lambda file: (tf.data.TextLineDataset(file).skip(1).window(size=temporal_series_length, shift=windowing_shift, drop_remainder=True)))

  #each window being a dataset, make them a single batch to recover a timeseries sample
  dataset = datasets.flat_map(lambda x:x.batch(temporal_series_length, drop_remainder=True))
  
  # decode csv lines
  dataset = dataset.map(decode_csv, num_parallel_calls=tf.data.AUTOTUNE, deterministic=not(shuffle))

  # apply filter if provided
  if post_proc_filter is not None:
    dataset=dataset.filter(post_proc_filter)  

  if shuffle:
    dataset=dataset.shuffle(batch_size*100)
    
  return dataset.batch(batch_size, drop_remainder=True).prefetch(buffer_size=tf.data.AUTOTUNE)

def FileListProcessor_image_classification(sourceFolder, file_extension,
                                           use_alternative_imread=False,
                                           image_reader_flags=-1,
                                           shuffle_batches=True,
                                           batch_size=1,
                                           debug=False):
  """
  Loads a set of images from a folder with associated labels for image classification.


  :param sourceFolder : The parent folder of the target files.
  :param file_extension : The target file extension.
  :param use_alternative_imread : Set False to read from Tensorflow native ops or set 'gdal' or 'opencv' to read with those tools.
  :param image_reader_flags : Set -1 to use defaults or add specific flags to provide to the image readers.
  :param shuffle_batches : Set True to shuffle false to keep order.
  :param batch_size : An indicatr batch size to dimension the prefectch queue.
  :param device : The device where to put the dataset provider (better to set on CPU ("/cpu:0")).
  :param debug: Boolean, if True, prints additionnal logs.
  """
  raise NotImplementedError('FileListProcessor_image_classification is not yet implemented')
  ds = tf.data.Dataset.list_files(os.path.join(sourceFolder,file_extension))
  ds = ds.map(map_func=load_image)

  if shuffle_batches is True:
    dataset=dataset.shuffle(batch_size*100)

  dataset=dataset.batch(batch_size).prefetch(size=tf.data.AUTOTUNE)  # Make sure you always have 1 batch ready to serve

  return dataset
