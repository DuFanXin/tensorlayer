#! /usr/bin/python
# -*- coding: utf8 -*-

""" tl.prepro for data augmentation """

import tensorflow as tf
import tensorlayer as tl
from tensorlayer.layers import set_keep
import numpy as np
import time, os, io
from PIL import Image

sess = tf.InteractiveSession()

X_train, y_train, X_test, y_test = tl.files.load_cifar10_dataset(
                                    shape=(-1, 32, 32, 3), plotable=False)
scale = X_train.max()
X_train /= scale
X_test /= scale

def model(x, y_, is_train, reuse):
    W_init = tf.truncated_normal_initializer(stddev=5e-2)
    W_init2 = tf.truncated_normal_initializer(stddev=0.04)
    b_init2 = tf.constant_initializer(value=0.1)
    with tf.variable_scope("model", reuse=reuse):
        tl.layers.set_name_reuse(reuse)
        network = tl.layers.InputLayer(x, name='input')

        network = tl.layers.Conv2dLayer(network, act=tf.identity,
                    shape=[5, 5, 3, 64], strides=[1, 1, 1, 1], padding='SAME', # 64 features for each 5x5x3 patch
                    W_init=W_init, b_init=None, name='cnn1')                            # output: (batch_size, 24, 24, 64)
        network = tl.layers.BatchNormLayer(network, is_train=is_train,
                    act=tf.nn.relu, name='batch1')
        network = tl.layers.PoolLayer(network, ksize=[1, 3, 3, 1],
                    strides=[1, 2, 2, 1], padding='SAME',
                    pool=tf.nn.max_pool, name='pool1',)               # output: (batch_size, 12, 12, 64)

        network = tl.layers.Conv2dLayer(network, act=tf.identity,
                    shape=[5, 5, 64, 64], strides=[1, 1, 1, 1], padding='SAME',# 64 features for each 5x5 patch
                    W_init=W_init, b_init=None, name ='cnn2')         # output: (batch_size, 12, 12, 64)
        network = tl.layers.BatchNormLayer(network, is_train=is_train,
                    act=tf.nn.relu, name='batch2')
        network = tl.layers.PoolLayer(network, ksize=[1, 3, 3, 1],
                    strides=[1, 2, 2, 1], padding='SAME',
                    pool = tf.nn.max_pool, name ='pool2')             # output: (batch_size, 6, 6, 64)

        network = tl.layers.FlattenLayer(network, name='flatten')     # output: (batch_size, 2304)
        network = tl.layers.DenseLayer(network, n_units=384, act=tf.nn.relu,
                    W_init=W_init2, b_init=b_init2, name='relu1')           # output: (batch_size, 384)
        network = tl.layers.DenseLayer(network, n_units=192, act = tf.nn.relu,
                    W_init=W_init2, b_init=b_init2, name='relu2')           # output: (batch_size, 192)
        network = tl.layers.DenseLayer(network, n_units=10, act = tf.identity,
                    W_init=tf.truncated_normal_initializer(stddev=1/192.0),
                    b_init = tf.constant_initializer(value=0.0),
                    name='output')                                    # output: (batch_size, 10)
        y = network.outputs
        cost = tl.cost.cross_entropy(y, y_, name='cost')
        L2 = tf.contrib.layers.l2_regularizer(0.004)(network.all_params[4]) + \
                tf.contrib.layers.l2_regularizer(0.004)(network.all_params[6])
        cost = cost + L2
        correct_prediction = tf.equal(tf.argmax(y, 1), y_)
        acc = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))

        return network, cost, acc

def distort_fn(x, is_train=False):
    """
    Description
    -----------
    The images are processed as follows:
    .. They are cropped to 24 x 24 pixels, centrally for evaluation or randomly for training.
    .. They are approximately whitened to make the model insensitive to dynamic range.
    For training, we additionally apply a series of random distortions to
    artificially increase the data set size:
    .. Randomly flip the image from left to right.
    .. Randomly distort the image brightness.
    .. Randomly zoom in.
    """
    x = tl.prepro.crop(x, 24, 24, is_random=is_train)
    if is_train:
        x = tl.prepro.zoom(x, zoom_range=(0.9, 1.0), is_random=True)
        x = tl.prepro.flip_axis(x, axis=1, is_random=True)
        x = tl.prepro.brightness(x, gamma=0.2, gain=1, is_random=True)
    return x

x = tf.placeholder(tf.float32, shape=[None, 24, 24, 3], name='x')
y_ = tf.placeholder(tf.int64, shape=[None, ], name='y_')

network, cost, _ = model(x, y_, True, False)
_, cost_test, acc = model(x, y_, False, True)

## train
n_epoch = 50000
learning_rate = 0.0001
print_freq = 1
batch_size = 128

train_params = network.all_params
train_op = tf.train.AdamOptimizer(learning_rate, beta1=0.9, beta2=0.999,
    epsilon=1e-08, use_locking=False).minimize(cost, var_list=train_params)

tl.layers.initialize_global_variables(sess)

network.print_params(False)
network.print_layers()

print('   learning_rate: %f' % learning_rate)
print('   batch_size: %d' % batch_size)

for epoch in range(n_epoch):
    start_time = time.time()
    for X_train_a, y_train_a in tl.iterate.minibatches(
                                X_train, y_train, batch_size, shuffle=True):
        X_train_a = tl.prepro.threading_data(X_train_a, fn=distort_fn, is_train=True)  # data augmentation for training
        sess.run(train_op, feed_dict={x: X_train_a, y_: y_train_a})

    if epoch + 1 == 1 or (epoch + 1) % print_freq == 0:
        print("Epoch %d of %d took %fs" % (epoch + 1, n_epoch, time.time() - start_time))
        train_loss, train_acc, n_batch = 0, 0, 0
        for X_train_a, y_train_a in tl.iterate.minibatches(
                                X_train, y_train, batch_size, shuffle=True):
            X_train_a = tl.prepro.threading_data(X_train_a, fn=distort_fn, is_train=False)  # central crop
            err, ac = sess.run([cost_test, acc], feed_dict={x: X_train_a, y_: y_train_a})
            train_loss += err; train_acc += ac; n_batch += 1
        print("   train loss: %f" % (train_loss/ n_batch))
        print("   train acc: %f" % (train_acc/ n_batch))
        test_loss, test_acc, n_batch = 0, 0, 0
        for X_test_a, y_test_a in tl.iterate.minibatches(
                                    X_test, y_test, batch_size, shuffle=True):
            X_test_a = tl.prepro.threading_data(X_test_a, fn=distort_fn, is_train=False)   # central crop
            err, ac = sess.run([cost_test, acc], feed_dict={x: X_test_a, y_: y_test_a})
            test_loss += err; test_acc += ac; n_batch += 1
        print("   test loss: %f" % (test_loss/ n_batch))
        print("   test acc: %f" % (test_acc/ n_batch))