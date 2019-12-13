import numpy as np
# import matplotlib.pyplot as plt
import struct

FS = 44100
TABLE_LENGTH = 44100
HD_TABLE_LENGTH = TABLE_LENGTH*100
x = np.arange(TABLE_LENGTH)
hdx = np.arange(HD_TABLE_LENGTH)

"""
Keyboard key to note dictionary
"""
KEY2NOTE = {
    "z": "C",
    "s": "C#",
    "x": "D",
    "d": "D#",
    "c": "E",
    "v": "F",
    "g": "F#",
    "b": "G",
    "h": "G#",
    "n": "A",
    "j": "A#",
    "m": "B",
    ",": "C",
    "l": "C#",
    ".": "D",
    ";": "D#",
    "/": "E",
}

"""
Keyboard key to midi number dictionary
"""
KEY2NUMBER = {
    "z": 1,
    "s": 2,
    "x": 3,
    "d": 4,
    "c": 5,
    "v": 6,
    "g": 7,
    "b": 8,
    "h": 9,
    "n": 10,
    "j": 11,
    "m": 12,
    "q": 13,
    "2": 14,
    "w": 15,
    "3": 16,
    "e": 17,
    "r": 18,
    "5": 19,
    "t": 20,
    "6": 21,
    "y": 22,
    "7": 23,
    "u": 24,
    "i": 25,
}

"""
Note-frequency dictionary
"""
NOTE2FREQ = {
    "C": 16.35,
    "C#": 17.32,
    "Db": 17.32,
    "D": 18.35,
    "D#": 19.45,
    "Eb": 19.45,
    "E": 20.60,
    "F": 21.83,
    "F#": 23.12,
    "Gb": 23.12,
    "G": 24.50,
    "G#": 25.96,
    "Ab": 25.96,
    "A": 27.50,
    "A#": 29.14,
    "Bb": 29.14,
    "B": 30.87
}

"""
Note-frequency dictionary
"""
NUMBER2FREQ = {
    1: 16.35,
    2: 17.32,
    3: 18.35,
    4: 19.45,
    5: 20.60,
    6: 21.83,
    7: 23.12,
    8: 24.50,
    9: 25.96,
    10: 27.50,
    11: 29.14,
    12: 30.87
}

"""
Note-number dictionary
"""
NOTE2NUMBER = {
    "C": 1,
    "C#": 2,
    "Db": 2,
    "D": 3,
    "D#": 4,
    "Eb": 4,
    "E": 5,
    "F": 6,
    "F#": 7,
    "Gb": 7,
    "G": 8,
    "G#": 9,
    "Ab": 9,
    "A": 10,
    "A#": 11,
    "Bb": 11,
    "B": 12
}

"""
Number-note dictionary
"""
NUMBER2NOTE = {
    1: "C",
    2: "C#",
    3: "D",
    4: "D#",
    5: "E",
    6: "F",
    7: "F#",
    8: "G",
    9: "G#",
    10: "A" ,
    11: "A#" ,
    12: "B"
}

"""
Wavetables
paFloat32 formatted
"""
def sinTable():
    return np.sin((2*np.pi/TABLE_LENGTH)*x)

def triTable():
    tab = (4.0/(TABLE_LENGTH)*x)
    tab[int(TABLE_LENGTH/4):int(TABLE_LENGTH/2)] = 1-tab[0:int(TABLE_LENGTH/4)]
    tab[int(TABLE_LENGTH/2):]=-1*tab[0:int(TABLE_LENGTH/2)]
    return tab

def sawTable():
    tab = (2.0/(TABLE_LENGTH))*x
    tab[int(TABLE_LENGTH/2):] = tab[int(TABLE_LENGTH/2):] - 2
    return tab

def sqrTable():
    return np.sign(TABLE_LENGTH/2-x)

def noiseTable():
    return np.random.random(TABLE_LENGTH)

def hdSinTable():
    return np.sin((2*np.pi/(HD_TABLE_LENGTH))*hdx)

def hdTriTable():
    tab = (4.0/(HD_TABLE_LENGTH)*hdx)
    tab[int(HD_TABLE_LENGTH/4):int(HD_TABLE_LENGTH/2)] = 1-tab[0:int(HD_TABLE_LENGTH/4)]
    tab[int(HD_TABLE_LENGTH/2):]=-1*tab[0:int(HD_TABLE_LENGTH/2)]
    return tab

def hdSawTable():
    tab = (2.0/(HD_TABLE_LENGTH))*hdx
    tab[int(HD_TABLE_LENGTH/2):] = tab[int(HD_TABLE_LENGTH/2):] - 2
    return tab

def hdSqrTable():
    return np.sign(HD_TABLE_LENGTH/2-hdx)

def hdNoiseTable():
    return np.random.random(HD_TABLE_LENGTH)

"""
Old Int16 tables
Sounded bad for some reason
"""
# def sinTable():
#     return (32767*np.sin((2*np.pi/TABLE_LENGTH)*x) + 32768).astype(np.uint16)
#
# def triTable():
#     tab = (4.0/(TABLE_LENGTH)*x)*32767 + 32768
#     tab[int(TABLE_LENGTH/4):int(TABLE_LENGTH/2)] = 32767-tab[0:int(TABLE_LENGTH/4)]
#     tab[int(TABLE_LENGTH/2):]=-1*tab[0:int(TABLE_LENGTH/2)]
#     return tab.astype(np.uint16)
#
# def sawTable():
#     tab = ((2.0/(TABLE_LENGTH))*x)*32767 + 32768
#     tab[int(TABLE_LENGTH/2):] = tab[int(TABLE_LENGTH/2):] - 2*32767+1
#     return tab.astype(np.uint16)
#
# def sqrTable():
#     return (32767*np.sign(TABLE_LENGTH/2-x) + 32768).astype(np.uint16)
#
# def noiseTable():
#     return (32767*np.random.random(TABLE_LENGTH) + 32768).astype(np.uint16)

if __name__=="__main__":
    plt.plot(x,noiseTable())
    plt.show()
