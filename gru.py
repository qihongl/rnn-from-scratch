import tensorflow as tf
import numpy as np

import utils
import data.shakespeare.datagen as data

import random
import argparse
import sys

class GRU_rnn():

    def __init__(self, state_size, num_classes, seqlen,
            ckpt_path='ckpt/gru1/',
            model_name='gru1'):

        self.state_size = state_size
        self.num_classes = num_classes
        self.seqlen = seqlen
        self.ckpt_path = ckpt_path
        self.model_name = model_name

        # build graph ops
        def __graph__():
            tf.reset_default_graph()
            # inputs
            xs_ = tf.placeholder(shape=[None], dtype=tf.int32)
            ys_ = tf.placeholder(shape=[None], dtype=tf.int32)
            #
            # embeddings
            embs = tf.get_variable('emb', [num_classes, state_size])
            rnn_inputs = tf.nn.embedding_lookup(embs, xs_)
            #
            # initial hidden state
            init_state = tf.placeholder(shape=[state_size], dtype=tf.float32, name='initial_state')
            #
            # here comes the scan operation; wake up!
            states = tf.scan(step, rnn_inputs, initializer=init_state) # tf.scan(fn, elems, initializer)
            #
            # predictions
            V = tf.get_variable('V', shape=[state_size, num_classes], 
                                initializer=tf.contrib.layers.xavier_initializer())
            bo = tf.get_variable('bo', shape=[num_classes], 
                                 initializer=tf.constant_initializer(0.))
            logits = tf.matmul(states,V) + bo
            last_state = states[-1]
            predictions = tf.nn.softmax(logits)
            #
            # optimization
            losses = tf.nn.sparse_softmax_cross_entropy_with_logits(logits, ys_)
            loss = tf.reduce_mean(losses)
            train_op = tf.train.AdamOptimizer(learning_rate=0.1).minimize(loss)
            #
            # expose variables
            self.xs_ = xs_
            self.ys_ = ys_
            self.loss = loss
            self.train_op = train_op
            self.predictions = predictions
            self.last_state = last_state
            self.init_state = init_state
        ####
        # step - GRU
        def step(st_1, x):
            # reshape vectors to matrices
            st_1 = tf.reshape(st_1, [1, self.state_size])
            x = tf.reshape(x, [1,self.state_size])
            # initializer
            xav_init = tf.contrib.layers.xavier_initializer
            # params
            W = tf.get_variable('W', shape=[3, self.state_size, self.state_size], initializer=xav_init())
            U = tf.get_variable('U', shape=[3, self.state_size, self.state_size], initializer=xav_init())
            b = tf.get_variable('b', shape=[self.state_size], initializer=tf.constant_initializer(0.))
            ####
            # GATES
            #
            #  update gate
            z = tf.sigmoid(tf.matmul(x,U[0]) + tf.matmul(st_1,W[0]))
            #  reset gate
            r = tf.sigmoid(tf.matmul(x,U[1]) + tf.matmul(st_1,W[1]))
            #  intermediate
            h = tf.tanh(tf.matmul(x,U[2]) + tf.matmul( (r*st_1),W[1]))
            ###
            # new state
            st = (1-z)*h + (z*st_1)
            st = tf.reshape(st, [self.state_size])
            return st
        ##### 
        # build graph
        sys.stdout.write('\n<log> Building Graph...')
        __graph__()
        sys.stdout.write('</log>\n')

    ####
    # training
    def train(self, train_set, epochs=1000):
        # training session
        with tf.Session() as sess:
            sess.run(tf.global_variables_initializer())
            train_loss = 0
            try:
                for i in range(epochs):
                    for j in range(1000):
                        xs, ys = train_set.__next__()
                        _, train_loss_ = sess.run([self.train_op, self.loss], feed_dict = {
                                self.xs_ : xs.reshape([self.seqlen]),
                                self.ys_ : ys.reshape([self.seqlen]),
                                self.init_state : np.zeros([self.state_size])
                            })
                        train_loss += train_loss_
                    print('[{}] loss : {}'.format(i,train_loss/1000))
                    train_loss = 0
            except KeyboardInterrupt:
                print('interrupted by user at ' + str(i))
                #
                # training ends here; 
                #  save checkpoint
                saver = tf.train.Saver()
                saver.save(sess, self.ckpt_path + self.model_name, global_step=i)
    ####
    # generate characters
    def generate(self, idx2w, w2idx, num_words=100):
        #
        # generate text
        random_init_word = random.choice(idx2w)
        current_word = w2idx[random_init_word]
        #
        # start session
        with tf.Session() as sess:
            # init session
            sess.run(tf.global_variables_initializer())
            #
            # restore session
            ckpt = tf.train.get_checkpoint_state(self.ckpt_path)
            saver = tf.train.Saver()
            if ckpt and ckpt.model_checkpoint_path:
                saver.restore(sess, ckpt.model_checkpoint_path)
            # generate operation
            words = [current_word]
            state = None
            # enter the loop
            for i in range(num_words):
                if state:
                    feed_dict = {self.xs_ : [current_word], self.init_state : state_}
                else:
                    feed_dict = {self.xs_ : [current_word], self.init_state : np.zeros([self.state_size])}
                #
                # forward propagation
                preds, state_ = sess.run([self.predictions, self.last_state], feed_dict=feed_dict)
                # 
                # set flag to true
                state = True
                # 
                # set new word
                current_word = np.random.choice(preds.shape[-1], 1, p=np.squeeze(preds))[0]
                # add to list of words
                words.append(current_word)
        ########
        # return the list of words as string
        return ' '.join([idx2w[w] for w in words])

### 
# parse arguments
def parse_args():
    parser = argparse.ArgumentParser(
        description='Vanilla Recurrent Neural Network for Text Hallucination, built with tf.scan')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-g', '--generate', action='store_true',
                        help='generate text')
    group.add_argument('-t', '--train', action='store_true',
                        help='train model')
    parser.add_argument('-n', '--num_words', required=False, type=int,
                        help='number of words to generate')
    args = vars(parser.parse_args())
    return args


###
# main function
if __name__ == '__main__':
    # parse arguments
    args = parse_args()
    #
    # fetch data
    X, Y, idx2w, w2idx, seqlen = data.load_data('data/shakespeare/')
    #
    # create the model
    model = GRU_rnn(state_size = 512, num_classes=len(idx2w), seqlen=seqlen)
    # to train or to generate?
    if args['train']:
        # get train set
        train_set = utils.rand_batch_gen(X,Y,batch_size=1)
        #
        # start training
        model.train(train_set)
    elif args['generate']:
        # call generate method
        text = model.generate(idx2w, w2idx, 
                num_words=args['num_words'] if args['num_words'] else 100)
        #########
        # text generation complete
        #
        print('______Generated Text_______')
        print(text)
        print('___________________________')