# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, division

import numpy as np
import scipy.ndimage
import tensorflow as tf

from niftynet.engine.input_buffer import InputBatchQueueRunner
from niftynet.io.image_window import ImageWindow, N_SPATIAL
from niftynet.layer.base_layer import Layer


class ResizeSampler(Layer, InputBatchQueueRunner):
    """
    This class generates samples by rescaling the whole image to the desired size
    currently 4D input is supported, Height x Width x Depth x Modality
    """

    def __init__(self, reader, data_param, batch_size, windows_per_image):

        self.reader = reader
        Layer.__init__(self, name='input_buffer')
        capacity = max(batch_size * 4, windows_per_image * 4)
        InputBatchQueueRunner.__init__(self,
                                       capacity=capacity,
                                       shuffle=True)
        tf.logging.info('reading size of preprocessed images')
        self.window = ImageWindow.from_data_reader_properties(
            self.reader.input_sources,
            self.reader.shapes,
            self.reader.tf_dtypes,
            data_param)
        tf.logging.info('initialised window instance')
        self._create_queue_and_ops(self.window,
                                   enqueue_size=1,
                                   dequeue_size=batch_size)
        tf.logging.info("initialised sampler output {} "
                        " [-1 for dynamic size]".format(self.window.shapes))

    def layer_op(self, *args, **kwargs):
        """
        This function generates sampling windows to the input buffer
        image data are from self.reader()
        it first completes window shapes based on image data,
        then finds random coordinates based on the window shapes
        finally resize each image as window and output
        a dictionary (required by input buffer)
        :return: output data dictionary {placeholders: data_array}
        """
        while True:
            image_id, data, interp_orders = self.reader()
            if not data:
                break
            image_shapes = {
                name: data[name].shape for name in self.window.fields}
            # window shapes can be dynamic, here they
            # are converted to static ones
            # as now we know the image shapes
            static_window_shapes = self.window.match_image_shapes(image_shapes)

            # for resize sampler the coordinates are not used
            # simply use the spatial dims of the input image
            all_coordinates = dummy_coordinates(image_id, image_shapes)

            output_dict = {}
            for name in list(data):
                # prepare output dictionary keys
                coordinates_key = self.window.coordinates_placeholder(name)
                image_data_key = self.window.image_data_placeholder(name)

                # prepare coordinates data
                output_dict[coordinates_key] = all_coordinates[name]

                # prepare image data
                image_shape = image_shapes[name]
                window_shape = static_window_shapes[name]
                zoom_ratio = [p / d for p, d in zip(window_shape, image_shape)]
                image_window = scipy.ndimage.interpolation.zoom(
                    data[name], zoom_ratio, order=interp_orders[name][0])
                output_dict[image_data_key] = image_window[np.newaxis, ...]
            # the output image shape should be
            # [enqueue_batch_size, x, y, z, time, modality]
            # here enqueue_batch_size = 1 as we only have one sample
            # per image
            yield output_dict


def dummy_coordinates(image_id, image_sizes):
    """
    This function returns a set of image window coordinates
    which are just from 0 to image_shapes
    """
    all_coordinates = {}
    for mod in list(image_sizes):
        coords = []
        coords.append(
            [image_id] + [0, 0, 0] + list(image_sizes[mod][:N_SPATIAL]))
        all_coordinates[mod] = np.asarray(coords)
    return all_coordinates
