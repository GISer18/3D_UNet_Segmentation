import numpy as np 
import os
import keras.layers
from keras import backend as keras
from keras.models import Model
from keras.layers import Input, concatenate, Conv3D, MaxPooling3D, UpSampling3D
from keras.optimizers import Adam


def unet(input_size=None, label_nums=30): #slices = 224
    if input_size is None:
        input_size = (64, 64, 64, 1)
    inputs = Input(input_size)

    conv1 = Conv3D(16, 3, activation = 'relu', padding = 'same', data_format ="channels_last", kernel_initializer='he_normal')(inputs)
    conv1 = Conv3D(32, 3, activation = 'relu', padding = 'same', data_format ="channels_last", kernel_initializer='he_normal')(conv1)
    
    pool1 = MaxPooling3D(pool_size=(2,2,2), data_format ="channels_last")(conv1)
    conv2 = Conv3D(32, 3, activation ='relu', padding = 'same', data_format ="channels_last", kernel_initializer='he_normal')(pool1)
    conv2 = Conv3D(64, 3, activation ='relu', padding = 'same', data_format ="channels_last", kernel_initializer='he_normal')(conv2)

    pool2 = MaxPooling3D(pool_size=(2,2,2), data_format ="channels_last")(conv2)
    conv3 = Conv3D(64, 3, activation ='relu', padding = 'same', data_format ="channels_last", kernel_initializer='he_normal')(pool2)
    conv3 = Conv3D(128, 3, activation ='relu', padding = 'same', data_format ="channels_last", kernel_initializer='he_normal')(conv3)

    pool3 = MaxPooling3D(pool_size=(2,2,2), data_format ="channels_last")(conv3)
    conv4 = Conv3D(128, 3, activation ='relu', padding = 'same', data_format ="channels_last", kernel_initializer='he_normal')(pool3)
    conv4 = Conv3D(256, 3, activation ='relu', padding = 'same', data_format ="channels_last", kernel_initializer='he_normal')(conv4)

    pool4 = MaxPooling3D(pool_size=(2,2,2), data_format ="channels_last")(conv4)
    conv5 = Conv3D(256, 3, activation ='relu', padding = 'same', data_format ="channels_last", kernel_initializer='he_normal')(pool4)
    conv5 = Conv3D(512, 3, activation ='relu', padding = 'same', data_format ="channels_last", kernel_initializer='he_normal')(conv5)

    up1 = UpSampling3D(size=(2,2,2), data_format ="channels_last")(conv5)
    up1 = concatenate([conv4,up1],axis=-1)
    conv6 = Conv3D(256, 3, activation = 'relu', padding = 'same', data_format ="channels_last", kernel_initializer='he_normal')(up1)
    conv6 = Conv3D(256, 3, activation = 'relu', padding = 'same', data_format ="channels_last", kernel_initializer='he_normal')(conv6)

    up2 = UpSampling3D(size=(2,2,2), data_format ="channels_last")(conv6)
    up2 = concatenate([conv3,up2],axis=-1)
    conv7 = Conv3D(128, 3, activation = 'relu', padding = 'same', data_format ="channels_last", kernel_initializer='he_normal')(up2)
    conv7 = Conv3D(128, 3, activation = 'relu', padding = 'same', data_format ="channels_last", kernel_initializer='he_normal')(conv7)

    up3 = UpSampling3D(size=(2,2,2), data_format ="channels_last")(conv7)
    up3 = concatenate([conv2,up3],axis=-1)
    conv8 = Conv3D(64, 3, activation = 'relu', padding = 'same', data_format ="channels_last", kernel_initializer='he_normal')(up3)
    conv8 = Conv3D(64, 3, activation = 'relu', padding = 'same', data_format ="channels_last", kernel_initializer='he_normal')(conv8)

    up4 = UpSampling3D(size=(2,2,2), data_format ="channels_last")(conv8)
    up4 = concatenate([conv1,up4],axis=-1)
    conv9 = Conv3D(32, 3, activation = 'relu', padding = 'same', data_format ="channels_last", kernel_initializer='he_normal')(up4)
    conv9 = Conv3D(32, 3, activation = 'relu', padding = 'same', data_format ="channels_last", kernel_initializer='he_normal')(conv9)

    conv10 = Conv3D(label_nums, 1, activation='softmax')(conv9)

    return Model(input=inputs, output=conv10)

'''
Functions below is from Dr.Adrian Dalca's Neuron toolbox
https://github.com/voxelmorph/voxelmorph/tree/master/ext/neuron
'''

"""
tensorflow/keras utilities for the neuron project
If you use this code, please cite 
Dalca AV, Guttag J, Sabuncu MR
Anatomical Priors in Convolutional Networks for Unsupervised Biomedical Segmentation, 
CVPR 2018
or for the transformation/integration functions:
Unsupervised Learning for Fast Probabilistic Diffeomorphic Registration
Adrian V. Dalca, Guha Balakrishnan, John Guttag, Mert R. Sabuncu
MICCAI 2018.
Contact: adalca [at] csail [dot] mit [dot] edu
License: GPLv3
"""

# third party
from keras import backend as K
from keras.legacy import interfaces
import keras
from keras.layers import Layer, InputLayer, Input
import tensorflow as tf
from keras.engine.topology import Node


# # local
from utils import transform, affine_to_shift


class SpatialTransformer(Layer):
    """
    N-D Spatial Transformer Tensorflow / Keras Layer
    The Layer can handle both affine and dense transforms. 
    Both transforms are meant to give a 'shift' from the current position.
    Therefore, a dense transform gives displacements (not absolute locations) at each voxel,
    and an affine transform gives the *difference* of the affine matrix from 
    the identity matrix.
    If you find this function useful, please cite:
      Unsupervised Learning for Fast Probabilistic Diffeomorphic Registration
      Adrian V. Dalca, Guha Balakrishnan, John Guttag, Mert R. Sabuncu
      MICCAI 2018.
    Originally, this code was based on voxelmorph code, which 
    was in turn transformed to be dense with the help of (affine) STN code 
    via https://github.com/kevinzakka/spatial-transformer-network
    Since then, we've re-written the code to be generalized to any 
    dimensions, and along the way wrote grid and interpolation functions
    """

    def __init__(self,
                 interp_method='linear',
                 indexing='ij',
                 single_transform=False,
                 **kwargs):
        """
        Parameters: 
            interp_method: 'linear' or 'nearest'
            single_transform: whether a single transform supplied for the whole batch
            indexing (default: 'ij'): 'ij' (matrix) or 'xy' (cartesian)
                'xy' indexing will have the first two entries of the flow 
                (along last axis) flipped compared to 'ij' indexing
        """
        self.interp_method = interp_method
        self.ndims = None
        self.inshape = None
        self.single_transform = single_transform

        assert indexing in ['ij', 'xy'], "indexing has to be 'ij' (matrix) or 'xy' (cartesian)"
        self.indexing = indexing

        super(self.__class__, self).__init__(**kwargs)


    def build(self, input_shape):
        """
        input_shape should be a list for two inputs:
        input1: image.
        input2: transform Tensor
            if affine:
                should be a N x N+1 matrix
                *or* a N*N+1 tensor (which will be reshape to N x (N+1) and an identity row added)
            if not affine:
                should be a *vol_shape x N
        """

        if len(input_shape) > 2:
            raise Exception('Spatial Transformer must be called on a list of length 2.'
                            'First argument is the image, second is the transform.')
        
        # set up number of dimensions
        self.ndims = len(input_shape[0]) - 2
        self.inshape = input_shape
        vol_shape = input_shape[0][1:-1]
        trf_shape = input_shape[1][1:]

        # the transform is an affine iff:
        # it's a 1D Tensor [dense transforms need to be at least ndims + 1]
        # it's a 2D Tensor and shape == [N+1, N+1]. 
        #   [dense with N=1, which is the only one that could have a transform shape of 2, would be of size Mx1]
        self.is_affine = len(trf_shape) == 1 or \
                         (len(trf_shape) == 2 and all([f == (self.ndims+1) for f in trf_shape]))

        # check sizes
        if self.is_affine and len(trf_shape) == 1:
            ex = self.ndims * (self.ndims + 1)
            if trf_shape[0] != ex:
                raise Exception('Expected flattened affine of len %d but got %d'
                                % (ex, trf_shape[0]))

        if not self.is_affine:
            if trf_shape[-1] != self.ndims:
                raise Exception('Offset flow field size expected: %d, found: %d' 
                                % (self.ndims, trf_shape[-1]))

        # confirm built
        self.built = True

    def call(self, inputs):
        """
        Parameters
            inputs: list with two entries
        """

        # check shapes
        assert len(inputs) == 2, "inputs has to be len 2, found: %d" % len(inputs)
        vol = inputs[0]
        trf = inputs[1]

        # necessary for multi_gpu models...
        vol = K.reshape(vol, [-1, *self.inshape[0][1:]])
        trf = K.reshape(trf, [-1, *self.inshape[1][1:]])

        # go from affine
        if self.is_affine:
            trf = tf.map_fn(lambda x: self._single_aff_to_shift(x, vol.shape[1:-1]), trf, dtype=tf.float32)

        # prepare location shift
        if self.indexing == 'xy':  # shift the first two dimensions
            trf_split = tf.split(trf, trf.shape[-1], axis=-1)
            trf_lst = [trf_split[1], trf_split[0], *trf_split[2:]]
            trf = tf.concat(trf_lst, -1)

        # map transform across batch
        if self.single_transform:
            fn = lambda x: self._single_transform([x, trf[0,:]])
            return tf.map_fn(fn, vol, dtype=tf.float32)
        else:
            return tf.map_fn(self._single_transform, [vol, trf], dtype=tf.float32)

    def _single_aff_to_shift(self, trf, volshape):
        if len(trf.shape) == 1:  # go from vector to matrix
            trf = tf.reshape(trf, [self.ndims, self.ndims + 1])

        # note this is unnecessarily extra graph since at every batch entry we have a tf.eye graph
        trf += tf.eye(self.ndims+1)[:self.ndims,:]  # add identity, hence affine is a shift from identitiy
        return affine_to_shift(trf, volshape, shift_center=True)

    def _single_transform(self, inputs):
        return transform(inputs[0], inputs[1], interp_method=self.interp_method)