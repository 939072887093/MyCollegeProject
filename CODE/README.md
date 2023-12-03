# Ransomware Detector using Deep learning
A Deep Learning ensemble that classifies Windows executable files as either benign, ransomware, or other malware.


# Setup
This project uses Python 3. For the GUI detector program `goAntivirus.py`, the following python packages must be installed: tensorflow, keras, h5py, capstone, pefile, numpy, and scikit-learn. These can be installed via the terminal or command prompt command `pip install tensorflow keras h5py capstone pefile numpy scikit-learn`. Then simply run the script with `python goAntivirus.py`. You should be greeted by login page and after succefull login a file selection dialog with which you can select one or more '.exe' files, then click 'Open' and the deep learning ensemble will predict if they are benign, ransomware, or other malware.

Source code for training and pre-processing for the ensemble's two models, in the folders `bin-opcodes-vec` and `bin-utf8-vec`, should run with the same pre-requisites, though `tensorflow-gpu` is recommended to acheive reasonable training times.

# Abstract
This project demostrates a novel approach to detecting ransomware targeted at Microsoft Windows,
combining 2 deep learning neural network classifiers to create an ensemble, taking files as input in
Microsoft’s standard PE file format, such as those with a ‘.exe’ file extension, and returning a
prediction of the file belonging to 1 of 3 classes: benign, generic malware, or ransomware. The
model’s ability to distinguish between ransomware and other forms of malware allows it to be
applied as an extension to an existing malware detection system such as anti-virus software, and aid
in the categorisation and reverse engineering of new in-the-wild ransomware samples. The
ensemble automates static analysis of Windows software binaries by extracting features from the
contents of the files and abstracting patterns within these features. The results of testing the
ensemble model on data not seen in its training suggest a high level of predictive power in
classifying new in-the-wild samples.

