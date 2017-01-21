'''
Created on Nov, 2016

@author: hugo

'''
from __future__ import absolute_import

from keras.layers import Input, Dense, Lambda
from keras.models import Model
from keras.optimizers import Adadelta, Adam
from keras.models import load_model
from keras import regularizers
from keras import objectives
from keras.callbacks import EarlyStopping, ReduceLROnPlateau
from keras.layers.advanced_activations import PReLU
import keras.backend as K
# import tensorflow as tf

from ..utils.keras_utils import Dense_tied
from ..utils.io_utils import dump_json, load_json


class VarAutoEncoder(object):
    """VarAutoEncoder for topic modeling.

        Parameters
        ----------
        dim : dimensionality of encoding space.

        nb_epoch :

        batch_size :

        """

    def __init__(self, input_size, intermediate_dim, dim, batch_size=100, weights_file=None, epsilon_std=1.0):
        self.input_size = input_size
        self.intermediate_dim = intermediate_dim
        self.latent_dim = dim
        self.batch_size = batch_size
        self.epsilon_std = epsilon_std

        self.build(weights_file)

    def build(self, weights_file=None):
        input_layer = Input(shape=(self.input_size,))
        # input_layer = Input(batch_shape=(self.batch_size, self.input_size))
        hidden_layer1 = Dense(self.intermediate_dim, init='glorot_normal', activation='sigmoid')
        # hidden_layer1 = Dense(self.intermediate_dim, batch_input_shape=(None, self.input_size), init='glorot_normal', activation='sigmoid')
        h1 = hidden_layer1(input_layer)
        self.z_mean = Dense(self.latent_dim, init='glorot_normal')(h1)
        # self.z_mean = Dense(self.latent_dim, batch_input_shape=(None, self.intermediate_dim), init='glorot_normal')(h1)
        self.z_log_var = Dense(self.latent_dim, init='glorot_normal')(h1)
        # self.z_log_var = Dense(self.latent_dim, batch_input_shape=(None, self.intermediate_dim), init='glorot_normal')(h1)

        # note that "output_shape" isn't necessary with the TensorFlow backend
        latent_layer = Lambda(self.sampling, output_shape=(self.latent_dim,))([self.z_mean, self.z_log_var])

        # we instantiate these layers separately so as to reuse them later
        decoder_h = Dense(self.intermediate_dim, init='glorot_normal', activation='sigmoid')
        # decoder_h = Dense(self.intermediate_dim, batch_input_shape=(None, self.latent_dim), init='glorot_normal', activation='sigmoid')
        h_decoded = decoder_h(latent_layer)
        decoder_mean = Dense_tied(self.input_size, init='glorot_normal', activation='sigmoid', tied_to=hidden_layer1)
        x_decoded_mean = decoder_mean(h_decoded)

        self.vae = Model(input_layer, x_decoded_mean)
        # build a model to project inputs on the latent space
        self.encoder = Model(input_layer, self.z_mean)

        # build a digit generator that can sample from the learned distribution
        decoder_input = Input(shape=(self.latent_dim,))
        _h_decoded = decoder_h(decoder_input)
        _x_decoded_mean = decoder_mean(_h_decoded)
        self.decoder = Model(decoder_input, _x_decoded_mean)

        if not weights_file is None:
            self.vae.load_weights(weights_file, by_name=True)
            print 'Loaded pretrained weights'

    def fit(self, train_X, val_X, nb_epoch=50):
        print 'Training variational autoencoder'
        # optimizer = Adadelta(lr=1.)
        # optimizer = 'rmsprop'
        optimizer = Adadelta(lr=1.5)
        self.vae.compile(optimizer=optimizer, loss=self.vae_loss)

        self.vae.fit(train_X[0], train_X[1],
                shuffle=True,
                nb_epoch=nb_epoch,
                batch_size=self.batch_size,
                validation_data=(val_X[0], val_X[1]),
                callbacks=[ReduceLROnPlateau(monitor='val_loss', factor=0.2, patience=3, min_lr=0.01),
                            EarlyStopping(monitor='val_loss', min_delta=1e-5, patience=5, verbose=1, mode='auto')
                        ]
                )



        return self

    def vae_loss(self, x, x_decoded_mean):
        xent_loss = objectives.binary_crossentropy(x, x_decoded_mean)
        # xent_loss = self.input_size * objectives.binary_crossentropy(x, x_decoded_mean)
        kl_loss = - 0.5 * K.sum(1 + self.z_log_var - K.square(self.z_mean) - K.exp(self.z_log_var), axis=-1)
        return xent_loss + kl_loss

    # def weighted_vae_loss(self, feature_weights):
    #     def loss(y_true, y_pred):
    #         try:
    #             x = K.binary_crossentropy(y_pred, y_true)
    #             y = tf.Variable(feature_weights.astype('float32'))
    #             # y2 = y_true / K.sum(y_true)
    #             # import pdb;pdb.set_trace()
    #             xent_loss = K.dot(x, y)
    #             kl_loss = - 0.5 * K.sum(1 + self.z_log_var - K.square(self.z_mean) - K.exp(self.z_log_var), axis=-1)
    #         except Exception as e:
    #             print e
    #             import pdb;pdb.set_trace()
    #         return xent_loss + kl_loss
    #     return loss

    def sampling(self, args):
        z_mean, z_log_var = args
        epsilon = K.random_normal(shape=(self.batch_size, self.latent_dim), mean=0.,
                                  std=self.epsilon_std)
        return z_mean + K.exp(z_log_var / 2) * epsilon

def save_vae_model(model, arch_file, weights_file):
    arch = {'input_size': model.input_size,
            'intermediate_dim': model.intermediate_dim,
            'dim': model.latent_dim,
            'batch_size': model.batch_size}
    model.vae.save_weights(weights_file)
    dump_json(arch, arch_file)

def load_vae_model(model, arch_file, weights_file):
    arch = load_json(arch_file)
    ae = model(arch['input_size'], arch['intermediate_dim'], arch['dim'], arch['batch_size'], weights_file=weights_file)

    return ae
