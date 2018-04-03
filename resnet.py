import tensorflow as tf
import tensorflow.contrib.eager as tfe

# TODO: check regularization
# TODO: check resize-conv (upsampling)


class ResNeXt_Bottleneck(tfe.Network):
    def __init__(self,
                 filters_base,
                 project,
                 cardinality=32,
                 name='resnext_bottleneck'):
        assert filters_base % cardinality == 0
        assert project in [True, False, 'down']
        super().__init__(name=name)

        # identity
        if project == 'down':
            self.identity = self.track_layer(
                tfe.Sequential([
                    tf.layers.Conv2D(filters_base * 4, 2, 2,
                                     padding='same'),  # TODO: check this
                    tf.layers.BatchNormalization()
                ]))
        elif project:
            self.identity = self.track_layer(
                tfe.Sequential([
                    tf.layers.Conv2D(filters_base * 4, 1),
                    tf.layers.BatchNormalization()
                ]))
        else:
            self.identity = tf.identity

        # conv1
        self.conv1 = self.track_layer(tf.layers.Conv2D(filters_base * 2, 1))
        self.bn1 = self.track_layer(tf.layers.BatchNormalization())

        # conv2
        self.conv_bn2 = []
        for i in range(cardinality):
            strides = 2 if project == 'down' else 1

            conv2 = self.track_layer(
                tf.layers.Conv2D(
                    (filters_base * 2) // cardinality,
                    3,
                    strides,
                    padding='same'))
            bn2 = self.track_layer(tf.layers.BatchNormalization())
            self.conv_bn2.append((conv2, bn2))
            # TODO: refactor

        # conv3
        self.conv3 = self.track_layer(tf.layers.Conv2D(filters_base * 4, 1))
        self.bn3 = self.track_layer(tf.layers.BatchNormalization())

    def call(self, input, training):
        identity = self.identity(input)

        # conv1
        input = self.conv1(input)
        input = self.bn1(input, training)
        input = tf.nn.relu(input)

        # conv2
        splits = tf.split(input, len(self.conv_bn2), -1)
        assert len(splits) == len(self.conv_bn2)
        transformations = []
        for trans, (conv, bn) in zip(splits, self.conv_bn2):
            trans = conv(trans)
            trans = bn(trans, training)
            trans = tf.nn.relu(trans)
            transformations.append(trans)
        input = tf.concat(transformations, -1)

        # conv3
        input = self.conv3(input)
        input = self.bn3(input, training)
        input = input + identity
        input = tf.nn.relu(input)

        return input


class ResNeXt_Block(tfe.Sequential):
    def __init__(self, filters_base, depth, downsample, name='resnext_block'):
        layers = []

        for i in range(depth):
            if i == 0:
                project = 'down' if downsample else True
            else:
                project = False

            layer = ResNeXt_Bottleneck(
                filters_base, project=project, name='conv{}'.format(i + 1))

            layers.append(layer)

        super().__init__(layers, name=name)


class ResNeXt_Conv1(tfe.Network):
    def __init__(self, name='resnext_conv1'):
        super().__init__(name=name)

        self.conv = self.track_layer(
            tf.layers.Conv2D(64, 7, 2, padding='same', name='conv1'))
        self.bn = self.track_layer(tf.layers.BatchNormalization())

    def call(self, input, training):
        input = self.conv(input)
        input = self.bn(input, training)
        input = tf.nn.relu(input)

        return input


class ResNeXt(tfe.Network):
    def __init__(self, name='resnet'):
        super().__init__(name=name)

        self.conv1 = self.track_layer(ResNeXt_Conv1(name='conv1'))
        self.conv1_max_pool = self.track_layer(
            tf.layers.MaxPooling2D(3, 2, padding='same'))

    def call(self, input, training):
        input = self.conv1(input, training)
        C1 = input
        input = self.conv1_max_pool(input)
        input = self.conv2(input, training)
        C2 = input
        input = self.conv3(input, training)
        C3 = input
        input = self.conv4(input, training)
        C4 = input
        input = self.conv5(input, training)
        C5 = input

        return {'C1': C1, 'C2': C2, 'C3': C3, 'C4': C4, 'C5': C5}


class ResNeXt_50(ResNeXt):
    def __init__(self, name='resnet_v2_50'):
        super().__init__(name=name)

        self.conv2 = self.track_layer(
            ResNeXt_Block(
                filters_base=64, depth=3, downsample=False, name='conv2'))
        self.conv3 = self.track_layer(
            ResNeXt_Block(
                filters_base=128, depth=4, downsample=True, name='conv3'))
        self.conv4 = self.track_layer(
            ResNeXt_Block(
                filters_base=256, depth=6, downsample=True, name='conv4'))
        self.conv5 = self.track_layer(
            ResNeXt_Block(
                filters_base=512, depth=3, downsample=True, name='conv5'))
