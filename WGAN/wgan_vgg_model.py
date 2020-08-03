#encoding:utf-8
import os
import tensorflow as tf
import numpy as np
import time
from glob import glob
import inout_util as ut
import wgan_vgg_module as modules
import matplotlib.pyplot as plt
import SimpleITK as sitk
from random import shuffle


class wganVgg(object):
    def __init__(self, sess, args):
        self.sess = sess

        ####patients folder name
        #训练样本不包含测试样本
        self.train_patient_no = [d.split('/')[-1] for d in glob(args.dcm_path + '/*') if
                                 ('zip' not in d) & (d.split('/')[-1] not in args.test_patient_no)]
        print('self.train_patient_no',self.train_patient_no)
        self.test_patient_no = args.test_patient_no
        print('self.test_patient_no', self.test_patient_no)
        # save directory
        self.p_info = '_'.join(self.test_patient_no)
        self.checkpoint_dir = os.path.join(args.checkpoint_dir)
        self.log_dir = r'E:\pix2pix\WGAN_VGG3\logs'
        print('directory check!!\ncheckpoint : {}\ntensorboard_logs : {}'.format(self.checkpoint_dir, self.log_dir))

        #### set modules (generator, discriminator, vgg net)
        self.g_net = modules.generator
        self.d_net = modules.discriminator
        self.vgg = modules.Vgg19(vgg_path=args.pretrained_vgg)

        """
        load images
        """
        print('data load... dicom -> numpy')
        self.image_loader = ut.DCMDataLoader( \
            args.dcm_path, args.LDCT_path, args.NDCT_path, \
            image_size=args.whole_size, patch_size=args.patch_size, \
            depth=args.img_channel, image_max=args.trun_max, image_min=args.trun_min, \
            is_unpair=args.is_unpair, augument=args.augument, norm=args.norm)
        print('args.LDCT_path',args.LDCT_path)
        print('args.NDCT_path', args.NDCT_path)
        self.test_image_loader = ut.DCMDataLoader(
            args.dcm_path, args.LDCT_path, args.NDCT_path,\
            image_size=args.whole_size, patch_size=args.patch_size,\
            depth=args.img_channel, image_max=args.trun_max, image_min=args.trun_min,\
            is_unpair=args.is_unpair, augument=args.augument, norm=args.norm)

        t1 = time.time()
        if args.phase == 'train':
            self.image_loader(self.train_patient_no)
            print('self.train_patient_no',self.train_patient_no)
            print('test_patient_no',self.test_patient_no)
            self.test_image_loader(self.test_patient_no)
            print('data load complete !!!, {}\nN_train : {}, N_test : {}'.format(time.time() - t1,
                                                                                 len(self.image_loader.LDCT_image_name),
                                                                                 len(
                                                                                     self.test_image_loader.LDCT_image_name)))
        else:
            self.test_image_loader(self.test_patient_no)
            print('data load complete !!!, {}, N_test : {}'.format(time.time() - t1,
                                                                   len(self.test_image_loader.LDCT_image_name)))

        """
        build model
        """
        self.z_i = tf.placeholder(tf.float32, [None, args.patch_size, args.patch_size, args.img_channel],
                                  name='whole_LDCT')
        self.x_i = tf.placeholder(tf.float32, [None, args.patch_size, args.patch_size, args.img_channel],
                                  name='whole_LDCT')
        #### image placehold  (patch image, whole image)
        self.whole_z = tf.placeholder(tf.float32, [1, args.whole_size, args.whole_size, args.img_channel],
                                      name='whole_LDCT')
        self.whole_x = tf.placeholder(tf.float32, [1, args.whole_size, args.whole_size, args.img_channel],
                                      name='whole_NDCT')

        #### generate & discriminate
        # generated images
        self.G_zi = self.g_net(self.z_i, reuse=False)
        self.G_whole_zi = self.g_net(self.whole_z)

        # discriminate
        self.D_xi = self.d_net(self.x_i, reuse=False)
        self.D_G_zi = self.d_net(self.G_zi)

        #### loss define
        # gradients penalty
        self.epsilon = tf.random_uniform([], 0.0, 1.0)
        self.x_hat = self.epsilon * self.x_i + (1 - self.epsilon) * self.G_zi
        self.D_x_hat = self.d_net(self.x_hat)
        self.grad_x_hat = tf.gradients(self.D_x_hat, self.x_hat)[0]
        self.grad_x_hat_l2 = tf.sqrt(tf.reduce_sum(tf.square(self.grad_x_hat), axis=1))
        self.gradient_penalty = tf.square(self.grad_x_hat_l2 - 1.0)

        # perceptual loss
        self.G_zi_3c = tf.concat([self.G_zi] * 3, axis=3)
        self.xi_3c = tf.concat([self.x_i] * 3, axis=3)
        [w, h, d] = self.G_zi_3c.get_shape().as_list()[1:]
        self.vgg_perc_loss = tf.reduce_mean(tf.sqrt(tf.reduce_sum(
            tf.square((self.vgg.extract_feature(self.G_zi_3c) - self.vgg.extract_feature(self.xi_3c))))) / (w * h * d))

        # discriminator loss(WGAN LOSS)
        d_loss = tf.reduce_mean(self.D_G_zi) - tf.reduce_mean(self.D_xi)
        grad_penal = args.lambda_ * tf.reduce_mean(self.gradient_penalty)
        self.D_loss = d_loss + grad_penal
        # generator loss
        self.G_loss = args.lambda_1 * self.vgg_perc_loss - tf.reduce_mean(self.D_G_zi)

        #### variable list
        t_vars = tf.trainable_variables()
        self.d_vars = [var for var in t_vars if 'discriminator' in var.name]
        self.g_vars = [var for var in t_vars if 'generator' in var.name]

        """
        summary
        """
        # loss summary
        self.summary_vgg_perc_loss = tf.summary.scalar("1_PerceptualLoss_VGG", self.vgg_perc_loss)
        self.summary_d_loss_all = tf.summary.scalar("2_DiscriminatorLoss_WGAN", self.D_loss)
        self.summary_d_loss_1 = tf.summary.scalar("3_D_loss_disc", d_loss)
        self.summary_d_loss_2 = tf.summary.scalar("4_D_loss_gradient_penalty", grad_penal)
        self.summary_g_loss = tf.summary.scalar("GeneratorLoss", self.G_loss)
        self.summary_all_loss = tf.summary.merge(
            [self.summary_vgg_perc_loss, self.summary_d_loss_all, self.summary_d_loss_1, self.summary_d_loss_2,
             self.summary_g_loss])

        # psnr summary
        self.summary_psnr_ldct = tf.summary.scalar("1_psnr_LDCT", ut.tf_psnr(self.whole_z, self.whole_x, 1),
                                                   family='PSNR')  # 0 ~ 1
        self.summary_psnr_result = tf.summary.scalar("2_psnr_output", ut.tf_psnr(self.whole_x, self.G_whole_zi, 1),
                                                     family='PSNR')  # 0 ~ 1
        self.summary_psnr = tf.summary.merge([self.summary_psnr_ldct, self.summary_psnr_result])

        # image summary
        self.check_img_summary = tf.concat([tf.expand_dims(self.z_i[0], axis=0), \
                                            tf.expand_dims(self.x_i[0], axis=0), \
                                            tf.expand_dims(self.G_zi[0], axis=0)], axis=2)
        self.summary_train_image = tf.summary.image('0_train_image', self.check_img_summary)
        self.whole_img_summary = tf.concat([self.whole_z, self.whole_x, self.G_whole_zi], axis=2)
        self.summary_image = tf.summary.image('1_whole_image', self.whole_img_summary)

        #### optimizer
        self.d_adam, self.g_adam = None, None
        with tf.control_dependencies(tf.get_collection(tf.GraphKeys.UPDATE_OPS)):
            self.d_adam = tf.train.AdamOptimizer(learning_rate=args.alpha, beta1=args.beta1, beta2=args.beta2).minimize(
                self.D_loss, var_list=self.d_vars)
            self.g_adam = tf.train.AdamOptimizer(learning_rate=args.alpha, beta1=args.beta1, beta2=args.beta2).minimize(
                self.G_loss, var_list=self.g_vars)

        # model saver
        self.saver = tf.train.Saver(max_to_keep=None)

        print('--------------------------------------------\n# of parameters : {} '. \
              format(np.sum([np.prod(v.get_shape().as_list()) for v in tf.trainable_variables()])))

    def train(self, args):
        self.sess.run(tf.global_variables_initializer())
        print('self.log_dir', self.log_dir)
        print('self.sess.graph', self.sess.graph)
        self.writer = tf.summary.FileWriter(self.log_dir, self.sess.graph)

        self.start_step = 0
        if args.continue_train:
            if self.load():
                print(" [*] Load SUCCESS")
            else:
                print(" [!] Load failed...")

        print('Start point : iter : {}'.format(self.start_step))

        start_time = time.time()
        for t in range(self.start_step, args.num_iter):
            for _ in range(0, args.d_iters):
                # get input images
                real_sample_z, real_sample_x = self.image_loader.preproc_input(args)

                # discriminator update
                self.sess.run(self.d_adam, \
                              feed_dict={self.z_i: real_sample_z, \
                                         self.x_i: real_sample_x})
            # get input images
            real_sample_z, real_sample_x = self.image_loader.preproc_input(args)

            # generator update & loss summary
            _, summary_str = self.sess.run([self.g_adam, self.summary_all_loss], \
                                           feed_dict={self.z_i: real_sample_z, \
                                                      self.x_i: real_sample_x})
            self.writer.add_summary(summary_str, t)

            # print point
            if (t + 1) % args.print_freq == 0:
                # print loss & time
                d_loss, g_loss, g_zi_img, summary_str0 = self.sess.run( \
                    [self.D_loss, self.G_loss, self.G_zi, self.summary_train_image], \
                    feed_dict={self.z_i: real_sample_z, \
                               self.x_i: real_sample_x})
                # training sample check
                self.writer.add_summary(summary_str0, t)

                print('Iter {} Time {} d_loss {} g_loss {}'.format(t, time.time() - start_time, d_loss, g_loss))
                self.check_sample(args, t)

            if (t + 1) % args.save_freq == 0:
                self.save(args, t)
        self.save(args, t)

    # summary test sample image during training
    def check_sample(self, args, t):
        # summary whole image'
        sltd_idx = np.random.choice(range(len(self.test_image_loader.LDCT_images)))
        test_zi, test_xi = self.test_image_loader.LDCT_images[sltd_idx], self.test_image_loader.NDCT_images[sltd_idx]

        whole_G_zi = self.sess.run(self.G_whole_zi,
                                   feed_dict={self.whole_z: test_zi.reshape(self.whole_z.get_shape().as_list())})

        summary_str1, summary_str2 = self.sess.run([self.summary_image, self.summary_psnr], \
                                                   feed_dict={self.whole_z: test_zi.reshape(
                                                       self.whole_z.get_shape().as_list()), \
                                                              self.whole_x: test_xi.reshape(
                                                                  self.whole_x.get_shape().as_list()), \
                                                              self.G_whole_zi: whole_G_zi.reshape(
                                                                  self.G_whole_zi.get_shape().as_list()),
                                                              })
        self.writer.add_summary(summary_str1, t)
        self.writer.add_summary(summary_str2, t)

    def save(self, args, step):
        model_name = args.model + ".model"
        if not os.path.exists(self.checkpoint_dir):
            print('self.checkpoint_dir',self.checkpoint_dir)
            os.makedirs(self.checkpoint_dir)

        self.saver.save(self.sess,
                        os.path.join(self.checkpoint_dir, model_name),
                        global_step=step)

    def load(self):
        print(" [*] Reading checkpoint...")
        ckpt = tf.train.get_checkpoint_state(self.checkpoint_dir)
        if ckpt and ckpt.model_checkpoint_path:
            ckpt_name = os.path.basename(ckpt.model_checkpoint_path)
            self.start_step = int(ckpt_name.split('-')[-1])
            self.saver.restore(self.sess, os.path.join(self.checkpoint_dir, ckpt_name))
            print('self.start_step',self.start_step)
            return True
        else:
            return False

    def test(self, args):
        self.sess.run(tf.global_variables_initializer())

        if self.load():
            print(" [*] Load SUCCESS")
        else:
            print(" [!] Load failed...")

        ## mk save dir (image & numpy file)
        npy_save_dir = args.test_npy_save_dir
        print('npy_save_dir', npy_save_dir)
        if not os.path.exists(npy_save_dir):
            os.makedirs(npy_save_dir)

        ## test
        start_time = time.time()
        for idx in range(len(self.test_image_loader.LDCT_images)):
            test_zi, test_xi \
                = self.test_image_loader.LDCT_images[idx], self.test_image_loader.NDCT_images[idx]

            whole_G_zi = self.sess.run(self.G_whole_zi, \
                                       feed_dict={self.whole_z: test_zi.reshape(self.whole_z.get_shape().as_list())})

            # save_file_nm_f = 'from_' + self.test_image_loader.LDCT_image_name[idx]
            # save_file_nm_t = 'to_' + self.test_image_loader.NDCT_image_name[idx]
            save_file_nm_g = 'Gen_from_' + self.test_image_loader.LDCT_image_name[idx]

            # save_file_nm_f = save_file_nm_f.replace('C:/Users/admin/Desktop/pix2pix/', '')
            # save_file_nm_f = save_file_nm_f.replace('C:\\Users\\admin\Desktop\pix2pix\\', '')
            # save_file_nm_f = save_file_nm_f.replace('低剂量/', '')
            # save_file_nm_f = save_file_nm_f.replace('低剂量', 'low')
            # save_file_nm_f = save_file_nm_f.replace('曾锐', '1')
            # save_file_nm_f = save_file_nm_f.replace('陈成汉', '2')
            # save_file_nm_f = save_file_nm_f.replace('陈军', '3')
            # save_file_nm_f = save_file_nm_f.replace('陈丽莉', '4')
            # save_file_nm_f = save_file_nm_f.replace('陈锡溪', '5')
            # save_file_nm_f = save_file_nm_f.replace('陈新权', '6')
            # save_file_nm_f = save_file_nm_f.replace('低剂量\\', '')
            # save_file_nm_f = save_file_nm_f.replace('low\\', '')
            #
            # save_file_nm_t = save_file_nm_t.replace('C:/Users/admin/Desktop/pix2pix/', '')
            # save_file_nm_t = save_file_nm_t.replace('C:\\Users\\admin\Desktop\pix2pix\\', '')
            # save_file_nm_t = save_file_nm_t.replace('低剂量/', '')
            # save_file_nm_t = save_file_nm_t.replace('高剂量', 'high')
            # save_file_nm_t = save_file_nm_t.replace('曾锐', '1')
            # save_file_nm_t = save_file_nm_t.replace('陈成汉', '2')
            # save_file_nm_t = save_file_nm_t.replace('陈军', '3')
            # save_file_nm_t = save_file_nm_t.replace('陈丽莉', '4')
            # save_file_nm_t = save_file_nm_t.replace('陈锡溪', '5')
            # save_file_nm_t = save_file_nm_t.replace('陈新权', '6')
            # save_file_nm_t = save_file_nm_t.replace('陈新权', '6')
            # save_file_nm_t = save_file_nm_t.replace('低剂量\\', '')
            # save_file_nm_t = save_file_nm_t.replace('low\\', '')

            print('save_file_nm_g', save_file_nm_g)
            save_file_nm_g = save_file_nm_g.replace('E:/pix2pix/', '')
            save_file_nm_g = save_file_nm_g.replace('E:\\pix2pix\\', '')
            save_file_nm_g = save_file_nm_g.replace('低剂量/', '')
            save_file_nm_g = save_file_nm_g.replace('低剂量', 'low')
            save_file_nm_g = save_file_nm_g.replace('曾锐', '1')
            save_file_nm_g = save_file_nm_g.replace('陈成汉', '2')
            save_file_nm_g = save_file_nm_g.replace('陈军', '3')
            save_file_nm_g = save_file_nm_g.replace('陈丽莉', '4')
            save_file_nm_g = save_file_nm_g.replace('陈锡溪', '5')
            save_file_nm_g = save_file_nm_g.replace('陈新权', '6')
            save_file_nm_g = save_file_nm_g.replace('低剂量\\', '')
            save_file_nm_g = save_file_nm_g.replace('low\\', '')
            save_file_nm_g = save_file_nm_g.replace('Gen_from_test\\', 'Gen_from_test_')
            # print('save_file_nm_f', save_file_nm_f)
            # print('save_file_nm_t', save_file_nm_t)
            print('save_file_nm_g', save_file_nm_g)
            print('test_zi',test_zi.shape)
            whole_G_zi = whole_G_zi[0, :, :, 0]
            print('whole_G_zi', whole_G_zi.shape)
            print('test_xi', test_xi.shape)
            print('npy_save_dir', npy_save_dir)
            temp = np.concatenate((test_zi, whole_G_zi, test_xi), axis=1, out=None)
            temp = sitk.GetImageFromArray(temp)
            name = os.path.join(npy_save_dir, save_file_nm_g + '.nii')
            print(name)
            sitk.WriteImage(temp, name)
            # test_zi = sitk.GetImageFromArray(test_zi)
            # name_1 = os.path.join(npy_save_dir, save_file_nm_f + '.nii')
            # print(name_1)
            # sitk.WriteImage(test_zi, name_1)
            # test_xi = sitk.GetImageFromArray(test_xi)
            # name_2 = os.path.join(npy_save_dir, save_file_nm_t + '.nii')
            # print(name_2)
            # sitk.WriteImage(test_xi,name_2)
            # whole_G_zi = sitk.GetImageFromArray(whole_G_zi)
            # name_3 = os.path.join(npy_save_dir, save_file_nm_g + '.nii')
            # print(name_3)
            # sitk.WriteImage(whole_G_zi, name_3)

            #np.save(os.path.join(npy_save_dir, save_file_nm_f), test_zi)
            #np.save(os.path.join(npy_save_dir, save_file_nm_t), test_xi)
            np.save(os.path.join(npy_save_dir, save_file_nm_g), whole_G_zi)


