# -*- coding: utf-8 -*-

'''
@Author  :   Xu
 
@Software:   PyCharm
 
@File    :   classifier.py
 
@Time    :   2019-12-24 11:37
 
@Desc    :
 
'''

import os
import tensorflow as tf
from tensorflow import keras
import numpy as np
import multiprocessing

from bert4tf.tokenization.bert_tokenization import FullTokenizer
from bert4tf import BertModelLayer
from bert4tf.loader_bert import StockBertConfig, load_stock_weights


print(tf.__version__)
if tf.__version__.startswith("1."):
    tf.enable_eager_execution()


def read_tsv(path):
    with open(path, "r", encoding="utf8") as file:
        data = [d.strip().split("\t") for d in file.readlines()]
    return data


def split_x_y(data):
    x_train = [d[0] for d in data]
    y_train = [int(d[2]) for d in data]
    return x_train, y_train

def load_data():
    data_dir = "/Data/xiaobensuan/Datas/chineseGLUE/ccks2018_task3"
    train_data = read_tsv(os.path.join(data_dir, 'train.txt'))
    test_data = read_tsv(os.path.join(data_dir, 'test.txt'))
    dev_data = read_tsv(os.path.join(data_dir, 'dev.txt'))
    x_train, y_train = split_x_y(train_data)
    x_test, y_test = split_x_y(test_data)
    x_dev, y_dev = split_x_y(dev_data)
    assert len(x_train) == len(y_train)
    assert len(x_test) == len(y_test)
    assert len(x_dev) == len(y_dev)
    return x_train, y_train, x_test, y_test, x_dev, y_dev

def load_keras_model(model_dir, max_seq_length):
    '''

    :param model_dir:
    :param max_seq_length:
    :return:
    '''
    bert_config_file = os.path.join(model_dir, 'bert_config.json')
    bert_ckpt_file = os.path.join(model_dir, 'bert_model.ckpt')

    with tf.io.gfile.GFile(bert_config_file, 'r') as reader:
        bc = StockBertConfig.from_json_string(reader.read())
        l_bert = BertModelLayer.from_params(bc.to_bert_model_layer_params(), name='bert')

    inputs_ids = keras.layers.Input(shape=(max_seq_length,), dtype='int32', name='input_ids')
    token_type_ids = keras.layers.Input(shape=(max_seq_length,), dtype='int32', name='token_type_ids')

    l = l_bert([inputs_ids, token_type_ids])
    print('bert shape:', l)
    l = keras.layers.Lambda(lambda x: x[0])(l)

    output = keras.layers.Dense(1, activation=keras.activations.sigmoid)(l)

    model = keras.Model(inputs=[inputs_ids, token_type_ids], outputs=output)

    model.build(input_shape=[(None, max_seq_length),
                             (None, max_seq_length)
                            ])

    return model

def predict_on_keras_model(model_dir, inputs_ids, inputs_mask, token_type_ids):
    '''

    :param model_dir:
    :param inputs_ids:
    :param inputs_mask:
    :param token_type_ids:
    :return:
    '''
    max_seq_len = inputs_ids.shape[-1]

    model = load_keras_model(model_dir, max_seq_len)

    k_res = model.predict([inputs_ids, token_type_ids])
    return k_res

def tokenize_data(input_str_batch, max_seq_langth, model_dir):
    '''

    :param input_str_batch:
    :param max_seq_langth:
    :param model_dir:
    :return:
    '''
    tokenizer = FullTokenizer(vocab_file=os.path.join(model_dir, 'vocab.txt'), do_lower_case=True)
    input_ids_batch = []
    token_type_ids_batch = []
    for input_str in input_str_batch:
        input_tokens = tokenizer.tokenize(input_str)
        input_tokens = ["[CLS]"] + input_tokens + ["[SEP]"]

        # print("input_tokens len:", len(input_tokens))

        input_ids = tokenizer.convert_tokens_to_ids(input_tokens)
        if len(input_tokens) > max_seq_langth:
            input_ids = input_ids[:max_seq_langth]
        else:
            input_ids = input_ids + [0] * (max_seq_langth - len(input_tokens))
        token_type_ids = [0] * max_seq_langth
        input_ids_batch.append(input_ids)
        token_type_ids_batch.append(token_type_ids)

    return input_ids_batch, token_type_ids_batch

def test_finetune(model_dir):
    # 加载数据
    x_train, y_train, x_test, y_test, x_dev, y_dev = load_data()

    # 输入
    max_seq_len = len([d for d in x_train if len(d) > 256])

    pool = multiprocessing.Pool(3)
    results = []
    for data in [x_train, x_test, x_dev]:
        result = pool.apply_async(tokenize_data, args=[data, max_seq_len, model_dir])
        results.append(result.get())
    pool.close()
    pool.join()
    input_train_ids_batch, token_train_type_ids_batch = results[0]
    input_test_ids_batch, token_test_type_ids_batch = results[1]
    input_dev_ids_batch, token_dev_type_ids_batch = results[2]

    input_train_ids = np.array(input_train_ids_batch, dtype=np.int32)
    token_train_type_ids = np.array(token_train_type_ids_batch, dtype=np.int32)
    input_test_ids = np.array(input_test_ids_batch, dtype=np.int32)
    token_test_type_ids = np.array(token_test_type_ids_batch, dtype=np.int32)
    input_dev_ids = np.array(input_dev_ids_batch, dtype=np.int32)
    token_dev_type_ids = np.array(token_dev_type_ids_batch, dtype=np.int32)

    # print("   tokens:", input_tokens)
    # print("input_ids:{}/{}:{}".format(len(input_tokens), max_seq_len, input_ids), input_ids.shape, token_type_ids)

    model = load_keras_model(model_dir, max_seq_len)

    model.compile(optimizer=keras.optimizers.Adam(learning_rate=1e-5),
                  loss=keras.losses.binary_crossentropy,
                  metrics=['accuracy'])
    model.summary()

    model.fit(x=(input_train_ids, token_train_type_ids),
              y=y_train,
              batch_size=16,
              epochs=10,
              validation_data=((input_dev_ids, token_dev_type_ids), y_dev))

    model.evaluate((input_test_ids, token_test_type_ids))


if __name__ == "__main__":
    model_dir = '/Data/public/Bert/chinese_roberta_wwm_ext_L-12_H-768_A-12'
    test_finetune(model_dir)
