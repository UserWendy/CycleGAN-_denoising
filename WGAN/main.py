import argparse
import os
import sys
import tensorflow as tf
from time import time
sys.path.extend([os.path.abspath("."), os.path.abspath("./../..")])
import inout_util as ut
from wgan_vgg_model import  wganVgg
os.chdir(r'E:\pix2pix')
print('pwd : {}'.format(os.getcwd()))
test_dir = r'E:\pix2pix\低剂量'
test_name = ['曾锐', '陈成汉', '陈军', '陈丽莉', '陈锡溪', '陈新权']
test_patient = ''
for i in range(len(test_name)):
    test_patient = test_patient + (os.path.join(test_dir,test_name[i]) + ',')
test_patient = test_patient[:-1]
print('test_patient',test_patient)
parser = argparse.ArgumentParser(description='')
#set load directory
parser.add_argument('--dcm_path', dest='dcm_path', default= r'E:\pix2pix\低剂量', help='dicom file directory')
parser.add_argument('--LDCT_path', dest='LDCT_path', default= r'E:\pix2pix\低剂量', help='LDCT image folder name')
parser.add_argument('--NDCT_path', dest='NDCT_path', default= r'E:\pix2pix\高剂量', help='NDCT image folder name')
# parser.add_argument('--test_patient_no', dest='test_patient_no',type=ut.ParseList, default= 'C:/Users/admin/Desktop/pix2pix/低剂量/曾锐,C:/Users/admin/Desktop/pix2pix/test/低剂量/陈成汉')
parser.add_argument('--test_patient_no', dest='test_patient_no',type=ut.ParseList, default= test_patient)
parser.add_argument('--pretrained_vgg', dest='pretrained_vgg', default= r'E:\pix2pix\wgan_CT', help='pretrained vggnet directory(only wgan_vgg)')

#set save directory
parser.add_argument('--result', dest='result',  default=r'E:\pix2pix\WGAN_VGG3', help='save result dir(check point, test, log, summary params)')
parser.add_argument('--checkpoint_dir', dest='checkpoint_dir',  default=r'E:\pix2pix\WGAN_VGG3\model', help='check point dir')
parser.add_argument('--test_npy_save_dir', dest='test_npy_save_dir',  default=r'E:\pix2pix\WGAN_VGG3\output', help='test numpy file save dir')
parser.add_argument('--log_dir', dest='log_dir',  default='logs', help='test numpy file save dir')


#image info
parser.add_argument('--patch_size', dest='patch_size', type=int,  default=64, help='image patch size, h=w')
parser.add_argument('--whole_size', dest='whole_size', type=int,  default=512, help='image whole size, h=w')
parser.add_argument('--img_channel', dest='img_channel', type=int,  default=1, help='image channel, 1')
parser.add_argument('--trun_max', dest='trun_max', type=int, default=4000, help='truncated image max value')
parser.add_argument('--trun_min', dest='trun_min', type=int, default=-2000, help='truncated image min value')

#train, test
parser.add_argument('--phase', dest='phase', default='train', help='train or test')

#train detail
parser.add_argument('--augument', dest='augument',type=ut.ParseBoolean, default=False, help='augumentation')
parser.add_argument('--norm', dest='norm',  default='n01', help='normalization range, -1 ~ 1 : tanh, 0 ~ 1 :sigmoid' )
parser.add_argument('--is_unpair', dest='is_unpair', type=ut.ParseBoolean, default=False, help='unpaired image(cycle loss) : True|False')
parser.add_argument('--num_iter', dest = 'num_iter', type = int, default = 1000000, help = 'iterations')
parser.add_argument('--alpha', dest='alpha', type=float,  default=1e-5, help='learning rate')
parser.add_argument('--batch_size', dest='batch_size', type=int,  default=128, help='batch size')
parser.add_argument('--d_iters', dest='d_iters', type=int,  default=4, help='discriminator iteration')
parser.add_argument('--lambda_', dest='lambda_', type=int,  default=10, help='Gradient penalty term weight')
parser.add_argument('--lambda_1', dest='lambda_1', type=float,  default=0.1, help='Perceptual loss weight (in WGAN_VGG network)')
#parser.add_argument('--lambda_2', dest='lambda_2', type=float,  default=0.1, help='MSE loss weight(in WGAN_VGG network)')
parser.add_argument('--beta1', dest='beta1', type=float,  default=0.5, help='Adam optimizer parameter')
parser.add_argument('--beta2', dest='beta2', type=float,  default=0.9, help='Adam optimizer parameter')
parser.add_argument('--model', dest='model',  default='test', help='model name')

#others
parser.add_argument('--save_freq', dest='save_freq', type=int, default=1000000, help='save a model every save_freq (iteration)')
parser.add_argument('--print_freq', dest='print_freq', type=int, default=100, help='print_freq (iterations)')
parser.add_argument('--continue_train', dest='continue_train', type=ut.ParseBoolean, default=True, help='load the latest model: true, false')
parser.add_argument('--gpu_no', dest='gpu_no', type=int,  default=0, help='gpu no')

# -------------------------------------
args = parser.parse_args()
print(args)

os.environ["CUDA_VISIBLE_DEVICES"] = str(args.gpu_no)

tfconfig = tf.ConfigProto(allow_soft_placement=True)
tfconfig.gpu_options.allow_growth = True
sess = tf.Session(config=tfconfig)

print('train/test start!!')
t_start  = time()

model = wganVgg(sess, args)
print('finish model load')
model.train(args) if args.phase == 'train' else model.test(args)
if args.phase == 'train':
    params_summary = '{} complete!!, \ntime : {}\nset params : \n{}'.\
    format(args.phase, time() - t_start, args)
    print('params_summary',params_summary)
    with open(os.path.join(r'E:\pix2pix\WGAN_VGG3', "parameter_summary.txt"), "w") as text_file:
        text_file.write(params_summary)
