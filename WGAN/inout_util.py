import os
from glob import glob
import tensorflow as tf
import numpy as np
import matplotlib

matplotlib.use('Agg')
from matplotlib import pyplot as plt
from scipy.ndimage.interpolation import rotate
import dicom


class DCMDataLoader(object):
    def __init__(self, dcm_path, LDCT_image_path, NDCT_image_path, \
                 image_size=512, patch_size=64, depth=1, \
                 image_max=3072, image_min=-1024, batch_size=1, \
                 is_unpair=False, augument=False, norm='n01', num_threads=1, extension='IMA'):

        # dicom file dir
        self.extension = extension
        self.dcm_path = dcm_path
        self.LDCT_image_path = LDCT_image_path
        self.NDCT_image_path = NDCT_image_path

        # image params
        self.image_size = image_size
        self.patch_size = patch_size
        self.depth = depth

        self.image_max = image_max
        self.image_min = image_min

        # training params
        self.batch_size = batch_size
        self.is_unpair = is_unpair
        self.augument = augument
        self.norm = norm

        # CT slice name
        self.LDCT_image_name, self.NDCT_image_name = [], []

        # batch generator  prameters
        self.num_threads = num_threads
        self.capacity = 20 * self.num_threads * self.batch_size
        self.min_queue = 10 * self.num_threads * self.batch_size

    # dicom file -> numpy array
    def __call__(self, patent_no_list):
        p_LDCT = []
        p_NDCT = []
        for patent_no in patent_no_list:
            print('patent_no', patent_no)
            P_LDCT_path = os.listdir(patent_no)
            for i in P_LDCT_path:
                if 'DIRFILE' in i:
                    P_LDCT_path.remove(i)
            for i in range(len(P_LDCT_path)):
                P_LDCT_path[i] = os.path.join(patent_no + '/' + P_LDCT_path[i])
            patent_no_h = patent_no.replace('低', '高')
            print('patent_no_h',patent_no_h)
            p_NDCT_path = os.listdir(patent_no_h)
            for i in p_NDCT_path:
                if 'DIRFILE' in i:
                    p_NDCT_path.remove(i)
            for i in range(len(p_NDCT_path)):
                p_NDCT_path[i] = os.path.join(patent_no_h + '/' + p_NDCT_path[i])
            # load images
            org_LDCT_images, LDCT_slice_nm = self.get_pixels_hu(self.load_scan(P_LDCT_path),
                                                                '{}_{}'.format(patent_no, self.LDCT_image_path))
            org_NDCT_images, NDCT_slice_nm = self.get_pixels_hu(self.load_scan(p_NDCT_path),
                                                                '{}_{}'.format(patent_no, self.NDCT_image_path))

            # CT slice name
            self.LDCT_image_name.extend(LDCT_slice_nm)
            self.NDCT_image_name.extend(NDCT_slice_nm)

            # truncate & normalization
            p_LDCT.append(self.normalize(org_LDCT_images, self.image_max, self.image_min))
            p_NDCT.append(self.normalize(org_NDCT_images, self.image_max, self.image_min))

        self.LDCT_images = np.concatenate(tuple(p_LDCT), axis=0)
        self.NDCT_images = np.concatenate(tuple(p_NDCT), axis=0)

        # image index
        self.LDCT_index, self.NDCT_index = list(range(len(self.LDCT_images))), list(range(len(self.NDCT_images)))

    def load_scan(self, path):
        slices = [dicom.read_file(s) for s in path]
        slices.sort(key=lambda x: float(x.ImagePositionPatient[2]))
        try:
            slice_thickness = \
                np.abs(slices[0].ImagePositionPatient[2] - slices[1].ImagePositionPatient[2])
        except:
            slice_thickness = np.abs(slices[0].SliceLocation - slices[1].SliceLocation)
        for s in slices:
            s.SliceThickness = slice_thickness
        return slices

    def get_pixels_hu(self, slices, pre_fix_nm=''):
        image = np.stack([s.pixel_array for s in slices])
        image = image.astype(np.int16)
        image[image == -2000] = 0

        digit = 4
        slice_nm = []
        for slice_number in range(len(slices)):
            intercept = slices[slice_number].RescaleIntercept
            slope = slices[slice_number].RescaleSlope
            if slope != 1:
                image[slice_number] = slope * image[slice_number].astype(np.float32)
                image[slice_number] = image[slice_number].astype(np.int16)
            image[slice_number] += np.int16(intercept)

            # sorted(idx), sorted(d_idx)  -> [1, 10, 2], [ 0001, 0002, 0010]
            s_idx = str(slice_number)
            d_idx = '0' * (digit - len(s_idx)) + s_idx
            slice_nm.append(pre_fix_nm + '_' + d_idx)
        return np.array(image, dtype=np.int16), slice_nm

    def normalize(self, img, max_=3072, min_=-1024):
        img = img.astype(np.float32)
        img[img > max_] = max_
        img[img < min_] = min_
        if self.norm.lower() == 'n-11':  # -1 ~ 1
            img = 2 * ((img - min_) / (max_ - min_)) - 1
            return img
        else:  # 0 ~ 1
            img = (img - min_) / (max_ - min_)
            return img

    # RED CNN
    def augumentation(self, LDCT, NDCT):
        """
        sltd_random_indx[0] :
            1: rotation
            2. flipping
            3. scaling
            4. pass
        sltd_random_indx[1] :
            select 
        """
        sltd_random_indx = [np.random.choice(range(4)), np.random.choice(range(2))]
        if sltd_random_indx[0] == 0:
            return rotate(LDCT, 45, reshape=False), rotate(NDCT, 45, reshape=False)
        elif sltd_random_indx[0] == 1:
            param = [True, False][sltd_random_indx[1]]
            if param:
                return LDCT[:, ::-1], NDCT[:, ::-1]  # horizontal
            return LDCT[::-1, :], NDCT[::-1, :]  # vertical
        elif sltd_random_indx[0] == 2:
            param = [0.5, 2][sltd_random_indx[1]]
            return LDCT * param, NDCT * param
        elif sltd_random_indx[0] == 3:
            return LDCT, NDCT

    # WGAN_VGG, RED_CNN
    def get_randam_patches(self, LDCT_slice, NDCT_slice, patch_size, whole_size=512):
        whole_h = whole_w = whole_size
        h = w = patch_size

        # patch image range
        hd, hu = h // 2, int(whole_h - np.round(h / 2))
        wd, wu = w // 2, int(whole_w - np.round(w / 2))

        # patch image center(coordinate on whole image)
        h_pc, w_pc = np.random.choice(range(hd, hu + 1)), np.random.choice(range(wd, wu + 1))
        if len(LDCT_slice.shape) == 3:  # 3d patch
            LDCT_patch = LDCT_slice[:, h_pc - hd: int(h_pc + np.round(h / 2)), w_pc - wd: int(w_pc + np.round(h / 2))]
            NDCT_patch = NDCT_slice[:, h_pc - hd: int(h_pc + np.round(h / 2)), w_pc - wd: int(w_pc + np.round(h / 2))]
        else:  # 2d patch
            LDCT_patch = LDCT_slice[h_pc - hd: int(h_pc + np.round(h / 2)), w_pc - wd: int(w_pc + np.round(h / 2))]
            NDCT_patch = NDCT_slice[h_pc - hd: int(h_pc + np.round(h / 2)), w_pc - wd: int(w_pc + np.round(h / 2))]

        if self.augument:
            return self.augumentation(LDCT_patch, NDCT_patch)
        return LDCT_patch, NDCT_patch

    def preproc_input(self, args):
        LDCT_imgs, NDCT_imgs = [], []
        for i in range(self.batch_size):
            L_sltd_idx = np.random.choice(self.LDCT_index)
            N_sltd_idx = np.random.choice(self.NDCT_index)

            if self.patch_size != self.image_size:
                LDCT, NDCT = \
                    self.get_randam_patches(self.LDCT_images[L_sltd_idx], \
                                            self.NDCT_images[N_sltd_idx], args.patch_size)
            else:
                LDCT, NDCT = self.LDCT_images[L_sltd_idx], \
                             self.NDCT_images[N_sltd_idx]
            LDCT_imgs.append(np.expand_dims(LDCT, axis=-1))
            NDCT_imgs.append(np.expand_dims(NDCT, axis=-1))

        return np.array(LDCT_imgs), np.array(NDCT_imgs)


# ROI crop
def ROI_img(whole_image, row=[200, 350], col=[75, 225]):
    patch_ = whole_image[row[0]:row[1], col[0]: col[1]]
    return np.array(patch_)


# psnr
def log10(x):
    numerator = tf.log(x)
    denominator = tf.log(tf.constant(10, dtype=numerator.dtype))
    return numerator / denominator


def tf_psnr(img1, img2, PIXEL_MAX=255.0):
    mse = tf.reduce_mean((img1 - img2) ** 2)
    if mse == 0:
        return 100
    return 20 * log10(PIXEL_MAX / tf.sqrt(mse))


def psnr(img1, img2, PIXEL_MAX=255.0):
    mse = np.mean((img1 - img2) ** 2)
    if mse == 0:
        return 100
    return 20 * math.log10(PIXEL_MAX / math.sqrt(mse))


# save mk img
def save_image(LDCT, NDCT, output_, save_dir='.', max_=1, min_=0):
    f, axes = plt.subplots(2, 3, figsize=(30, 20))

    axes[0, 0].imshow(LDCT, cmap=plt.cm.gray, vmax=max_, vmin=min_)
    axes[0, 1].imshow(NDCT, cmap=plt.cm.gray, vmax=max_, vmin=min_)
    axes[0, 2].imshow(output_, cmap=plt.cm.gray, vmax=max_, vmin=min_)

    axes[1, 0].imshow(NDCT.astype(np.float32) - LDCT.astype(np.float32), cmap=plt.cm.gray, vmax=max_, vmin=min_)
    axes[1, 1].imshow(NDCT - output_, cmap=plt.cm.gray, vmax=max_, vmin=min_)
    axes[1, 2].imshow(output_ - LDCT, cmap=plt.cm.gray, vmax=max_, vmin=min_)

    axes[0, 0].title.set_text('LDCT image')
    axes[0, 1].title.set_text('NDCT image')
    axes[0, 2].title.set_text('output image')

    axes[1, 0].title.set_text('NDCT - LDCT  image')
    axes[1, 1].title.set_text('NDCT - outupt image')
    axes[1, 2].title.set_text('output - LDCT  image')
    if save_dir != '.':
        f.savefig(save_dir)
        plt.close()

    # ---------------------------------------------------


# argparser string -> boolean type
def ParseBoolean(b):
    b = b.lower()
    if b == 'true':
        return True
    elif b == 'false':
        return False
    else:
        raise ValueError('Cannot parse string into boolean.')


# argparser string -> boolean type
def ParseList(l):
    return l.split(',')