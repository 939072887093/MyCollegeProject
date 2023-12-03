import os, math, string, pefile, time, threading
import tkinter as tk
import numpy as np
from capstone import *
from tensorflow.keras.models import Sequential, Model
from keras.models import Input
from tensorflow.keras import layers, preprocessing
from tensorflow.keras.utils import Sequence
from sklearn.utils import shuffle
from tkinter import messagebox
from tkinter.filedialog import askopenfilenames, askdirectory
from tkinter.ttk import Progressbar
import getpass

## Defining models (opcode, strings, and ensemble)

# Defining the opcode model
opModel = Sequential(name="opcodeModel")

opModel.add(layers.InputLayer(input_shape=(50,)))
opModel.add(layers.Dense(256, activation='relu'))
opModel.add(layers.BatchNormalization())
opModel.add(layers.Dense(128, activation='relu'))
opModel.add(layers.BatchNormalization())
opModel.add(layers.Dense(64, activation='relu'))
opModel.add(layers.BatchNormalization())
opModel.add(layers.Dense(32, activation='relu'))
opModel.add(layers.BatchNormalization())
opModel.add(layers.Dense(16, activation='relu'))
opModel.add(layers.BatchNormalization())
opModel.add(layers.Dense(3, activation='softmax'))

opModel.load_weights("weights-improvement-574-0.85.hdf5")

opModel.compile(optimizer="rmsprop",
              loss='categorical_crossentropy',
              metrics=['accuracy'])


class histSequence(Sequence):

    def __init__(self, x, y, batch_size):
        self.x, self.y = shuffle(x, y)
        self.batch_size = batch_size

    def __len__(self):
        return math.ceil(len(self.x) / self.batch_size)

    def __getitem__(self, idx):
        batch_x = self.x[idx * self.batch_size:(idx + 1) *
        self.batch_size]
        batch_y = self.y[idx * self.batch_size:(idx + 1) *
        self.batch_size]

        return np.array([
            np.load(file_name)
            for file_name in batch_x]), np.array(batch_y)

    def on_epoch_end(self):
        pass


class histSequenceVal(histSequence):

    def __init__(self, x, y, batch_size):
        self.x, self.y = x, y
        self.batch_size = batch_size


# Defining the strings as greyscale images model
model = Sequential(name="stringsAsGreyscaleModel")

model.add(layers.InputLayer(input_shape=(100, 100, 1)))
model.add(layers.SpatialDropout2D(rate=0.2))
model.add(layers.Conv2D(32, kernel_size=3, activation='relu'))
model.add(layers.BatchNormalization())
model.add(layers.SpatialDropout2D(rate=0.1))
model.add(layers.Conv2D(16, kernel_size=3, activation='relu'))
model.add(layers.BatchNormalization())
model.add(layers.SpatialDropout2D(rate=0.1))
model.add(layers.Flatten())
model.add(layers.Dense(3, activation='softmax'))


class hashCorpusSequence(Sequence):

    def __init__(self, x, y, batch_size):
        self.x, self.y = shuffle(x, y)
        self.batch_size = batch_size

    def __len__(self):
        return math.ceil(len(self.x) / self.batch_size)

    def __getitem__(self, idx):
        batch_x = self.x[idx * self.batch_size:(idx + 1) *
        self.batch_size]
        batch_y = self.y[idx * self.batch_size:(idx + 1) *
        self.batch_size]

        return np.array([
            np.rint(((np.load(file_name) - np.min(np.load(file_name))) /
            (np.max(np.load(file_name)) - np.min(np.load(file_name)))) * 255).astype(int)
            for file_name in batch_x]), np.array(batch_y)

    def on_epoch_end(self):
        pass


class hashCorpusSequenceVal(hashCorpusSequence):

    def __init__(self, x, y, batch_size):
        self.x, self.y = x, y
        self.batch_size = batch_size


model.load_weights("weights-improvement-04-0.72.hdf5")

model.compile(optimizer="adamax",
              loss='categorical_crossentropy',
              metrics=['accuracy'])

#
# opModel.name = "opcodeModel"
# model.name = "stringsAsGreyscaleModel"

def ensemble(models, model_inputs):
    outputs = [models[0](model_inputs[0]), models[1](model_inputs[1])]
    y = layers.average(outputs)

    modelEns = Model(model_inputs, y, name='ensemble')

    return modelEns


models = [opModel, model]
model_inputs = [Input(shape=(50,)), Input(shape=(100, 100, 1))]
modelEns = ensemble(models, model_inputs)
modelEns.compile(optimizer='rmsprop', loss='categorical_crossentropy', metrics=['accuracy'])


## Pre-processing of PE (EXE, DLL, etc.) file(s)

# https://stackoverflow.com/questions/17195924/python-equivalent-of-unix-strings-utility
# Solution to Python based 'strings' alternative from SO. Decodes bytes of binary file as
# utf-8 strings
def strings(filename, min=4):
    with open(filename, errors="ignore", encoding="utf-8") as f:
        result = ""
        for c in f.read():
            if c in string.printable:
                result += c
                continue
            if len(result) >= min:
                yield result
            result = ""
        if len(result) >= min:  # catch result at EOF
            yield result


# Converting utf-8 string to sequence of words
def wordSequence(pePath):
    try:
        text = ""
        for s in strings(pePath):
            text += s + "\n"
        sequence = preprocessing.text.text_to_word_sequence(text)[:10000]
        return sequence
    except Exception as e:
        print(e)

# Hashing words of word sequences into sequences of word-specific integers
def hashWordSequences(sequences, maxSeqLen, vocabSize):

    hashedSeqs = []
    docCount = 0
    for sequence in sequences:
        try:
            text = " ".join(sequence)
            hashWordIDs = preprocessing.text.hashing_trick(text, round(vocabSize * 1.5), hash_function='md5')
            docLen = len(hashWordIDs)
            if docLen < maxSeqLen:
                hashWordIDs += [0 for i in range(0, maxSeqLen-docLen)]
            hashWordIDs = np.array(hashWordIDs).reshape(100, 100, 1)
            hashedSeqs.append(hashWordIDs)
            docCount += 1
        except Exception as e:
            print(e)
    return hashedSeqs


# Function takes list of paths to PE files and returns a list
# of lists, with the first index as input for the opcode model,
# and the second index as input for the strings model
def preprocessPEs(pePaths):
    mlInputs = []

    # Get percentage opcode composition of file assembley code for the top 50 most common opcodes
    # in each file
    opCodeSet = set()
    opCodeDicts = []
    opCodeFreqs = {}

    count = 1
    for sample in pePaths:
        try:
            pe = pefile.PE(sample, fast_load=True)
            entryPoint = pe.OPTIONAL_HEADER.AddressOfEntryPoint
            data = pe.get_memory_mapped_image()[entryPoint:]
            cs = Cs(CS_ARCH_X86, CS_MODE_32)

            opcodes = []
            for i in cs.disasm(data, 0x1000):
                opcodes.append(i.mnemonic)

            opcodeDict = {}
            total = len(opcodes)

            opCodeSet = set(list(opCodeSet) + opcodes)
            for opcode in opCodeSet:
                freq = 1
                for op in opcodes:
                    if opcode == op:
                        freq += 1
                try:
                    opCodeFreqs[opcode] += freq
                except:
                    opCodeFreqs[opcode] = freq

                opcodeDict[opcode] = round((freq / total) * 100, 2)

            opCodeDicts.append(opcodeDict)
            count += 1

        except Exception as e:
            print(e)

    opCodeFreqsSorted = np.genfromtxt("bin-opcodes-vec/top50opcodes.csv", delimiter=",", dtype="str")[1:, 0]

    count = 0
    for opDict in opCodeDicts:
        opFreqVec = []
        for opcode in opCodeFreqsSorted[:50]:
            try:
                opFreqVec.append(opDict[opcode])
            except Exception as e:
                if str(type(e)) == "<class 'KeyError'>":
                    opFreqVec.append(0.0)

        mlInputs.append([np.array(opFreqVec)])
        count += 1

    # Get words from utf-8 strings decoded from raw bytes of files,
    # and hash to vectors of integers
    sequences = []
    count = 0
    for sample in pePaths:
        sequences.append(wordSequence(sample))
        count += 1

    with open("bin-utf8-vec/finalVocabSize.txt", "r") as f:
        maxVocabSize = int(f.readline())

    hashSeqs = hashWordSequences(sequences, 10000, maxVocabSize)

    count = 0
    for hashSeq in hashSeqs:
        mlInputs[count].append(np.array(hashSeq))
        count += 1

    mlInputs = np.array(mlInputs)

    return mlInputs


## Function taking paths to PE files as input, and returning ensemble model predictions
# as output
def predictPEs(pePaths):
    classNames = ["benign", "malware", "ransomware"]
    pePredictions = {}

    count = 0
    for pePath in pePaths:
        x1 = preprocessPEs(pePaths)[count][0].reshape(1, 50)
        x2 = preprocessPEs(pePaths)[count][1].reshape(1, 100, 100, 1)
        count += 1
        pePredictions[pePath] = classNames[np.argmax(modelEns.predict(x=[x1, x2]))]

    return pePredictions

def executeAntivirus(root):
    # tkRoot = tk.Tk()
    tkRoot = root
    tkRoot.title("Scanning files...")
    tkRoot.withdraw()
    tkRoot.protocol("WM_DELETE_WINDOW", quit)
    w = tkRoot.winfo_screenwidth()
    h = tkRoot.winfo_screenheight()
    size = tuple(int(pos) for pos in tkRoot.geometry().split('+')[0].split('x'))
    x = w / 2 - size[0] / 2
    y = h / 2 - size[1] / 2
    tkRoot.geometry("300x1+{}+{}".format(round(x) - 150, round(y)))

    while True:
        try:
            # pePaths = list(askopenfilenames(filetypes=[("Windows executable files", "*.exe")]))
            user = getpass.getuser()
            fPath = askdirectory(initialdir='c:/Users/%s' % user)
            print(fPath)
            print(os.listdir(fPath))
            fPath_ls = os.listdir(fPath)
            pePaths = [os.path.join(fPath, path) for path in fPath_ls if path[-4:] == ".exe"]
            print("PePaths", pePaths)
            tkRoot.update()
            tkRoot.deiconify()
            preds = predictPEs(pePaths)
            if len(preds) > 0:
                classificationsStr = ""
                for key in preds.keys():
                    # print("'" + key + "'" + " detected as " + preds[key])
                    classificationsStr += "'" + key + "'" + " detected as " + preds[key] + "\n\n"
                tkRoot.withdraw()
                messagebox.showinfo("Detections", classificationsStr)
            else:
                quit()
        except Exception as e:
            messagebox.showerror("Error", "Error: " + str(e) + "\nPlease try again...")


class MainForm(tk.Frame):
    main_Root = None

    def destroyPackWidget(self, parent):
        for e in parent.pack_slaves():
            e.destroy()

    def __init__(self, master=None):
        MainForm.main_Root = master
        super().__init__(master=master)
        master.geometry("600x500")
        master.title("Account Login")
        self.createWidget()

    def createWidget(self):
        self.lblMsg = tk.Label(self, text="AntiVirus", bg="PeachPuff2", width="300", height="2",
                            font=("Calibri", 13))
        self.lblMsg.pack()
        self.btnLogin = tk.Button(self, text="Login", height="2", width="300", command=self.lblLogin_Click)
        self.btnLogin.pack()
        self.btnRegister = tk.Button(self, text="Register", height="2", width="300", command=self.btnRegister_Click)
        self.btnRegister.pack()

    def lblLogin_Click(self):
        self.destroyPackWidget(MainForm.main_Root)
        frmLogin = Login(MainForm.main_Root)
        frmLogin.pack()

    def btnRegister_Click(self):
        self.destroyPackWidget(MainForm.main_Root)
        frmSignUp = SignUp(MainForm.main_Root)
        frmSignUp.pack()


class Login(tk.Frame):
    main_Root = None

    def destroyPackWidget(self, parent):
        for e in parent.pack_slaves():
            e.destroy()

    def __init__(self, master=None):
        Login.main_Root = master
        super().__init__(master=master)
        master.title("Login")
        master.geometry("600x500")
        self.createWidget()

    def createWidget(self):
        self.lblMsg = tk.Label(self, text="Please enter details below to login", bg="blue")
        self.lblMsg.pack()
        self.username = tk.Label(self, text="Username * ")
        self.username.pack()
        self.username_verify = tk.StringVar()
        self.username_login_entry = tk.Entry(self, textvariable=self.username_verify)
        self.username_login_entry.pack()
        self.password = tk.Label(self, text="Password * ")
        self.password.pack()
        self.password_verify = tk.StringVar()
        self.password_login_entry = tk.Entry(self, textvariable=self.password_verify, show='*')
        self.password_login_entry.pack()
        self.btnLogin = tk.Button(self, text="Login", width=10, height=1, command=self.btnLogin_Click)
        self.btnLogin.pack()

    def btnLogin_Click(self):
        username1 = self.username_login_entry.get()
        password1 = self.password_login_entry.get()

        #        messagebox.showinfo("Failure", self.username1+":"+password1)
        list_of_files = os.listdir()
        if username1 in list_of_files:
            file1 = open(username1, "r")
            verify = file1.read().splitlines()
            if password1 in verify:
                messagebox.showinfo("Sucess", "Login Sucessful")
                self.destroyPackWidget(Login.main_Root)
                executeAntivirus(MainForm.main_Root)
            else:
                messagebox.showinfo("Failure", "Login Details are wrong try again")
        else:
            messagebox.showinfo("Failure", "User not found try from another user\n or sign up for new user")


class SignUp(tk.Frame):
    main_Root = None
    print("SignUp Class")

    def destroyPackWidget(self, parent):
        for e in parent.pack_slaves():
            e.destroy()

    def __init__(self, master=None):
        SignUp.main_Root = master
        master.title("Register")
        super().__init__(master=master)
        master.title("Register")
        master.geometry("600x500")
        self.createWidget()

    def createWidget(self):
        self.lblMsg = tk.Label(self, text="Please enter details below", bg="blue")
        self.lblMsg.pack()
        self.username_lable = tk.Label(self, text="Username * ")
        self.username_lable.pack()
        self.username = tk.StringVar()
        self.username_entry = tk.Entry(self, textvariable=self.username)
        self.username_entry.pack()

        self.password_lable = tk.Label(self, text="Password * ")
        self.password_lable.pack()
        self.password = tk.StringVar()
        self.password_entry = tk.Entry(self, textvariable=self.password, show='*')
        self.password_entry.pack()
        self.btnRegister = tk.Button(self, text="Register", width=10, height=1, bg="blue", command=self.register_user)
        self.btnRegister.pack()

    def register_user(self):
        file = open(self.username_entry.get(), "w")
        file.write(self.username_entry.get() + "\n")
        file.write(self.password_entry.get())
        file.close()

        self.destroyPackWidget(SignUp.main_Root)

        self.lblSucess = tk.Label(root, text="Registration Success", fg="green", font=("calibri", 11))
        self.lblSucess.pack()

        self.btnSucess = tk.Button(root, text="Click Here to proceed", command=self.btnSucess_Click)
        self.btnSucess.pack()

    def btnSucess_Click(self):
        self.destroyPackWidget(MainForm.main_Root)
        executeAntivirus()


if __name__ == "__main__":
    root = tk.Tk()
    frmMainForm = MainForm(root)
    frmMainForm.pack()
    root.mainloop()

