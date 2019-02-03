''' helpers_loss, a collection of helpers to compute various losses and related tools
    @author, Alexandre Benoit, LISTIC Lab, FRANCE
'''
# python 2&3 compatibility management
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import six

import tensorflow as tf
import numpy as np

################################

def multi_loss(lossesList):
  ''' refactored from the original work of Y. Gal https://github.com/yaringal/multi-task-learning-example/blob/master/multi-task-learning-example.ipynb
      Args:
        lossesList:the python list of dicts with keys ('loss_value', 'name') to combine
        logvars:   the list of associated prediction logvars
      Returns:
        the loss combination as a single scalar value
  '''
  output_logvars=[]
  for id, loss in enumerate(lossesList):
      #create a dedicated output log variance variable to regress
      logvar_name='task_uncertainty_'+str(loss['name'])
      log_var = tf.Variable(tf.constant(1.0, tf.float32), name=logvar_name)
      output_logvars.append(log_var)
      tf.summary.scalar(logvar_name, log_var)
      precision = tf.math.exp(-log_var)
      single_loss = precision * loss['loss_value'] + log_var
      print('single_loss='+str(single_loss))
      if id==0:
        loss_sum=single_loss
      else:
        loss_sum+=single_loss
  return tf.math.reduce_mean(loss_sum)

def reconstruction_loss_L1(inputs, reconstruction):
  with tf.name_scope('reconstruction_loss_l1'):
    inputs_flat = tf.layers.flatten(inputs)
    reconstruction_flat = tf.layers.flatten(reconstruction)
    # Reconstruction loss
    l1_loss=tf.reduce_mean(tf.abs(inputs_flat-reconstruction_flat))
    tf.summary.scalar('L1loss', l1_loss)
    #l1_loss=tf.Print(l1_loss, [l1_loss], message='l1_loss')
    return l1_loss

def reconstruction_loss_MSE(inputs, reconstruction):
  with tf.name_scope('reconstruction_loss_MSE'):
    inputs_flat = tf.layers.flatten(inputs)
    reconstruction_flat = tf.layers.flatten(reconstruction)
    # Reconstruction loss
    mse_loss=tf.losses.mean_squared_error(
                                    reconstruction,
                                    inputs,
                                    weights=1.0,
                                    scope=None,
                                    loss_collection=tf.GraphKeys.LOSSES,
                                    #reduction=tf.losses.Reduction.SUM_BY_NONZERO_WEIGHTS
                                    )
    tf.summary.scalar('MSE_loss', mse_loss)
    return mse_loss

def reconstruction_loss_BCE(inputs, reconstruction, pos_weight=1.):
  with tf.name_scope('reconstruction_loss_BCE'):
    inputs_flat = tf.layers.flatten(inputs)
    reconstruction_flat = tf.layers.flatten(reconstruction)
    '''xcross_loss=tf.reduce_mean(tf.nn.weighted_cross_entropy_with_logits( targets=inputs_flat,
                                              logits=reconstruction_flat,
                                              pos_weight=pos_weight))

    xcross_loss=tf.reduce_mean(xcross_loss)
    '''
    from keras import backend as K
    xcross_loss=K.mean(K.binary_crossentropy(inputs_flat,reconstruction_flat))

    tf.summary.scalar('reconstruction_loss_BCE', xcross_loss)
    #xcross_loss=tf.Print(xcross_loss, [xcross_loss], message='xcross_loss')
    return xcross_loss

def reconstruction_loss_BCE_soft(inputs, reconstruction, w=0.8):
  with tf.name_scope('reconstruction_loss_BCE_soft'):
    inputs_flat = tf.layers.flatten(inputs)
    reconstruction_flat = tf.layers.flatten(reconstruction)

    # handmade binary cross entropy loss taking into account the lower representation of the white pixels
    xcross_loss=-tf.reduce_mean(w * inputs_flat * tf.log(reconstruction_flat + 1e-8),
                                         reduction_indices=[1]) - \
                         tf.reduce_mean(
                             (1 - w) * (1 - inputs_flat) * tf.log(1 - reconstruction_flat + 1e-8),
                             reduction_indices=[1])

    xcross_loss=tf.reduce_mean(xcross_loss)
    tf.summary.scalar('reconstruction_loss_BCE_soft', xcross_loss)

    return xcross_loss

def kl_loss(z_mean, logvar, id):
  ''' KL loss between two distributions,
  an identifier 'id' is considered for visibility on Tensorboard '''
  with tf.name_scope('kl_Divergence_loss'):
    # KL Divergence loss
    kl_div_loss = 1. + logvar - tf.square(z_mean) - tf.exp(logvar)
    kl_div_loss = tf.reduce_mean(-0.5 * tf.reduce_mean(kl_div_loss, 1))
    tf.summary.scalar('VAE_kl_loss_'+str(id), kl_div_loss)
    #raw_input('VAE_kl_loss:'+str(kl_div_loss))
    return kl_div_loss

def generateTheta(L,endim):
  # This function generates L random samples from the unit `ndim'-u
  theta=[w/np.sqrt((w**2).sum()) for w in np.random.normal(size=(L,endim))]
  return np.asarray(theta, dtype=np.float32)

def generateZ_ring(batchsize):
  # This function generates 2D samples from a `circle' distribution in
  # a 2-dimensional space
  from sklearn.datasets import make_circles
  temp=make_circles(2*batchsize,noise=.01)
  return np.squeeze(temp[0][np.argwhere(temp[1]==0),:]).astype(np.float32)

def generateZ_circle(batchsize):
  # This function generates 2D samples from a `circle' distribution in
  # a 2-dimensional space
  r=np.random.uniform(size=(batchsize))
  theta=2*np.pi*np.random.uniform(size=(batchsize))
  x=r*np.cos(theta)
  y=r*np.sin(theta)
  z_=np.array([x,y], dtype=np.float32).T
  return z_

def slicedWasserteinLoss_single(code, target_z, sample_points, batch_size):
  import keras.backend as K
  # Let projae be the projection of the encoded samples
  projae=tf.matmul(code,tf.transpose(sample_points))
  # Let projz be the projection of the $q_Z$ samples
  #projz=K.dot(target_z,K.transpose(sample_points))
  projz=tf.matmul(target_z,tf.transpose(sample_points))
  #projz=tf.Print(projz, [projz, projz_tf], message='k vc tf')
  # Calculate the Sliced Wasserstein distance by sorting
  # the projections and calculating the L2 distance between
  W2=(tf.nn.top_k(tf.transpose(projae),k=batch_size).values-tf.nn.top_k(tf.transpose(projz),k=batch_size).values)**2
  #W2=tf.Print(W2, [tf.nn.top_k(tf.transpose(projae),k=batch_size).values[0]], message='sorted projae', summarize=10)
  w2weight=tf.Variable(tf.constant(10.0), trainable=False)
  tf.summary.scalar('W2_weight', w2weight)
  W2Loss= w2weight*tf.reduce_mean(W2)
  return W2Loss

def swae_loss(code_list, target_z, batch_size, L=50):
  '''Sliced Wasserstein Autoencodeur (AE) loss definition
    Args:
      inputs
      codes_list: a python list of AE codes
      reconstructed_data: the reconstructed data at the output of the AE
      L, the number of sample points to project on
  '''

  import keras.utils
  from keras.layers import Flatten
  from keras.layers import Reshape
  from keras import backend as K
  print('Setting up a Sliced Wasserstein loss following https://arxiv.org/abs/1804.01947')
  if len(code_list)==0:
    raise ValueError('swae_loss error : input code list is empty')
  if len(code_list[0].shape)!=2:
    raise ValueError('swae_loss error : input codes must be flat codes of size batchsize*codeDim')
  #generate two variables used for the loss at the current iteration
  #theta=tf.Variable(tf.ones(generateTheta(L,code_list[0].shape[-1]).shape), trainable=False) #Define a Keras Variable for \theta_ls
  #theta=tf.Print(theta, [theta], message='theta')
  #target_z=tf.Variable(tf.ones(target_z_samples.shape), trainable=False) #Define a Keras Variable for samples of z)
  theta=tf.py_func(generateTheta,[L, code_list[0].shape[-1]], tf.float32)
  #theta=tf.Print(theta, [theta, target_z], message='theta, target_z')

  loss=0
  for id, code in enumerate(tf.get_collection('codes')):
    W2Loss = slicedWasserteinLoss_single(code, target_z, theta, batch_size)
    tf.summary.scalar('w2loss_'+str(id), W2Loss)
    print('W2Loss='+str(W2Loss))
    loss+=W2Loss
  #loss=tf.Print(loss, [loss], message='SWAE')
  return loss