from pathlib import Path

from adidt.utils import tes


def test_treestruct_simple_int():
    raw = '''
type_t int = {
	.first_int = 1,
	.last_int = 0
}
    '''
    d = {
        'int': {
            'first_int': 1,
            'last_int': 0,
        },
    }

    t = tes.StructTree(name='int', pattern='type_t int =')
    t.parse(raw)

    assert t.data == d


def test_treestruct_simple_misc():
    raw = '''
type_t misc = {
	.pointer = &pointer,
	.define = DEFINE
}
    '''
    d = {
        'misc': {
            'pointer': '&pointer',
            'define': 'DEFINE',
        },
    }

    t = tes.StructTree(name='misc', pattern='type_t misc =')
    t.parse(raw)

    assert t.data == d


def test_treestruct_nested():
    raw = '''
type_t outer = {
	.inner = {
		.integer = 123,
		.define = DEFINE
	},
}
    '''
    d = {
        'outer': {
            'inner': {
                'integer': 123,
                'define': 'DEFINE',
            },
        },
    }

    t = tes.StructTree(name='outer', pattern='type_t outer =', children=[
        tes.StructTree(name='inner', pattern='.inner ='),
    ])
    t.parse(raw)

    assert t.data == d


def test_treestruct_nested_array():
    raw = '''
type_t outer = {
	.inner = {
		.integer = 123,
		.array = {1, 2, 3, 4, 5},
		.define = DEFINE
	},
}
    '''
    d = {
        'outer': {
            'inner': {
                'integer': 123,
                'array': [1, 2, 3, 4, 5],
                'define': 'DEFINE',
            },
        },
    }

    t = tes.StructTree(name='outer', pattern='type_t outer =', children=[
        tes.StructTree(name='inner', pattern='.inner =', children=[
            tes.StructTree(name='array', pattern='.array =', type='array'),
        ]),
    ])
    t.parse(raw)

    assert t.data == d


def test_parse_talise_config_c():
    file = Path(__file__).parent / 'adrv9009' / 'talise_config.c'
    exp = {
        'talInit': {
            'spiSettings': {
                'MSBFirst': 1,
                'enSpiStreaming': 0,
                'autoIncAddrUp': 1,
                'fourWireMode': 1,
                'cmosPadDrvStrength': 'TAL_CMOSPAD_DRV_2X',
            },
            'rx': {
                'rxProfile': {
                    'rxFir': {
                        'gain_dB': -6,
                        'numFirCoefs': 48,
                        'coefs': '&rxFirCoefs[0]',
                    },
                    'rxFirDecimation': 2,
                    'rxDec5Decimation': 4,
                    'rhb1Decimation': 2,
                    'rxOutputRate_kHz': 122880,
                    'rfBandwidth_Hz': 100000000,
                    'rxBbf3dBCorner_kHz': 100000,
                    'rxAdcProfile': [
                        265, 146, 181, 90, 1280, 366, 1257, 27, 1258, 17, 718, 39,
                        48, 46, 27, 161, 0, 0, 0, 0, 40, 0, 7, 6, 42, 0, 7, 6, 42,
                        0, 25, 27, 0, 0, 25, 27, 0, 0, 165, 44, 31, 905
                    ],
                    'rxDdcMode': 'TAL_RXDDC_BYPASS',
                    'rxNcoShifterCfg': {
                        'bandAInputBandWidth_kHz': 0,
                        'bandAInputCenterFreq_kHz': 0,
                        'bandANco1Freq_kHz': 0,
                        'bandANco2Freq_kHz': 0,
                        'bandBInputBandWidth_kHz': 0,
                        'bandBInputCenterFreq_kHz': 0,
                        'bandBNco1Freq_kHz': 0,
                        'bandBNco2Freq_kHz': 0,
                    },
                },
                'framerSel': 'TAL_FRAMER_A',
                'rxGainCtrl': {
                    'gainMode': 'TAL_MGC',
                    'rx1GainIndex': 255,
                    'rx2GainIndex': 255,
                    'rx1MaxGainIndex': 255,
                    'rx1MinGainIndex': 195,
                    'rx2MaxGainIndex': 255,
                    'rx2MinGainIndex': 195,
                },
                'rxChannels': 'TAL_RX1RX2',
            },
            'tx': {
                'txProfile': {
                    'dacDiv': 1,
                    'txFir': {
                        'gain_dB': 6,
                        'numFirCoefs': 80,
                        'coefs': '&txFirCoefs[0]',
                    },
                    'txFirInterpolation': 2,
                    'thb1Interpolation': 2,
                    'thb2Interpolation': 2,
                    'thb3Interpolation': 2,
                    'txInt5Interpolation': 1,
                    'txInputRate_kHz': 122880,
                    'primarySigBandwidth_Hz': 50000000,
                    'rfBandwidth_Hz': 100000000,
                    'txDac3dBCorner_kHz': 187000,
                    'txBbf3dBCorner_kHz': 56000,
                    'loopBackAdcProfile': [
                        265, 146, 181, 90, 1280, 366, 1257, 27, 1258, 17, 718, 39,
                        48, 46, 27, 161, 0, 0, 0, 0, 40, 0, 7, 6, 42, 0, 7, 6, 42,
                        0, 25, 27, 0, 0, 25, 27, 0, 0, 165, 44, 31, 905,
                    ],
                },
                'deframerSel': 'TAL_DEFRAMER_A',
                'txChannels': 'TAL_TX1TX2',
                'txAttenStepSize': 'TAL_TXATTEN_0P05_DB',
                'tx1Atten_mdB': 10000,
                'tx2Atten_mdB': 10000,
                'disTxDataIfPllUnlock': 'TAL_TXDIS_TX_RAMP_DOWN_TO_ZERO',
            },
            'obsRx': {
                'orxProfile': {
                    'rxFir': {
                        'gain_dB': 6,
                        'numFirCoefs': 48,
                        'coefs': '&obsrxFirCoefs[0]',
                    },
                    'rxFirDecimation': 2,
                    'rxDec5Decimation': 4,
                    'rhb1Decimation': 2,
                    'orxOutputRate_kHz': 122880,
                    'rfBandwidth_Hz': 100000000,
                    'rxBbf3dBCorner_kHz': 225000,
                    'orxLowPassAdcProfile': '{265',
                    # 'orxLowPassAdcProfile': [
                    #     265, 146, 181, 90, 1280, 366, 1257, 27, 1258, 17, 718, 39,
                    #     48, 46, 27, 161, 0, 0, 0, 0, 40, 0, 7, 6, 42, 0, 7, 6, 42,
                    #     0, 25, 27, 0, 0, 25, 27, 0, 0, 165, 44, 31, 905,
                    # ],
                    'orxBandPassAdcProfile': '{265',
                    # 'orxBandPassAdcProfile': [
                    #     265, 146, 181, 90, 1280, 366, 1257, 27, 1258, 17, 718,
                    #     39, 48, 46, 27, 161, 0, 0, 0, 0, 40, 0, 7, 6, 42, 0, 7,
                    #     6, 42, 0, 25, 27, 0, 0, 25, 27, 0, 0, 165, 44, 31, 905,
                    # ],
                    'orxDdcMode': 'TAL_ORXDDC_DISABLED',
                    'orxMergeFilter': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],

                },
                'orxGainCtrl': {
                    'gainMode': 'TAL_MGC',
                    'orx1GainIndex': 255,
                    'orx2GainIndex': 255,
                    'orx1MaxGainIndex': 255,
                    'orx1MinGainIndex': 195,
                    'orx2MaxGainIndex': 255,
                    'orx2MinGainIndex': 195,
                },
                'framerSel': 'TAL_FRAMER_B',
                'obsRxChannelsEnable': 'TAL_ORX1ORX2',
                'obsRxLoSource': 'TAL_OBSLO_RF_PLL',
            },
            'clocks': {
                'deviceClock_kHz': 122880,
                'clkPllVcoFreq_kHz': 9830400,
                'clkPllHsDiv': 'TAL_HSDIV_2P5',
                'rfPllUseExternalLo': 0,
                'rfPllPhaseSyncMode': 'TAL_RFPLLMCS_NOSYNC',
            },
            'jesd204Settings': {
                'framerA': {
                    'bankId': 1,
                    'deviceId': 0,
                    'lane0Id': 0,
                    'M': 4,
                    'K': 32,
                    'F': 4,
                    'Np': 16,
                    'scramble': 1,
                    'externalSysref': 1,
                    'serializerLanesEnabled': 3,
                    'serializerLaneCrossbar': 228,
                    'lmfcOffset': 31,
                    'newSysrefOnRelink': 0,
                    'syncbInSelect': 0,
                    'overSample': 0,
                    'syncbInLvdsMode': 1,
                    'syncbInLvdsPnInvert': 0,
                    'enableManualLaneXbar': 0,
                },
                'framerB': {
                    'bankId': 0,
                    'deviceId': 0,
                    'lane0Id': 0,
                    'M': 2,
                    'K': 32,
                    'F': 2,
                    'Np': 16,
                    'scramble': 1,
                    'externalSysref': 1,
                    'serializerLanesEnabled': 12,
                    'serializerLaneCrossbar': 228,
                    'lmfcOffset': 31,
                    'newSysrefOnRelink': 0,
                    'syncbInSelect': 1,
                    'overSample': 0,
                    'syncbInLvdsMode': 1,
                    'syncbInLvdsPnInvert': 0,
                    'enableManualLaneXbar': 0,
                },
                'deframerA': {
                    'bankId': 0,
                    'deviceId': 0,
                    'lane0Id': 0,
                    'M': 4,
                    'K': 32,
                    'scramble': 1,
                    'externalSysref': 1,
                    'deserializerLanesEnabled': 15,
                    'deserializerLaneCrossbar': 228,
                    'lmfcOffset': 17,
                    'newSysrefOnRelink': 0,
                    'syncbOutSelect': 0,
                    'Np': 16,
                    'syncbOutLvdsMode': 1,
                    'syncbOutLvdsPnInvert': 0,
                    'syncbOutCmosSlewRate': 0,
                    'syncbOutCmosDriveLevel': 0,
                    'enableManualLaneXbar': 0,
                },
                'deframerB': {
                    'bankId': 0,
                    'deviceId': 0,
                    'lane0Id': 0,
                    'M': 0,
                    'K': 32,
                    'scramble': 1,
                    'externalSysref': 1,
                    'deserializerLanesEnabled': 0,
                    'deserializerLaneCrossbar': 228,
                    'lmfcOffset': 0,
                    'newSysrefOnRelink': 0,
                    'syncbOutSelect': 1,
                    'Np': 16,
                    'syncbOutLvdsMode': 1,
                    'syncbOutLvdsPnInvert': 0,
                    'syncbOutCmosSlewRate': 0,
                    'syncbOutCmosDriveLevel': 0,
                    'enableManualLaneXbar': 0,
                },
                'serAmplitude': 15,
                'serPreEmphasis': 1,
                'serInvertLanePolarity': 0,
                'desInvertLanePolarity': 0,
                'desEqSetting': 1,
                'sysrefLvdsMode': 1,
                'sysrefLvdsPnInvert': 0,
            },
        },
    }

    tree = tes.parse_talise_config_c(file)

    for k in exp['talInit'].keys():
        print(k)
        assert tree.data['talInit'][k] == exp['talInit'][k]
