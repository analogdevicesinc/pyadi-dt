import xmltodict
from adidt.utils import profilewiz


def parse_profile(filename):
    nsxml = profilewiz.profile_to_xml(filename)
    profile = xmltodict.parse(nsxml)["adi_ad9528_Device_t"]

    pll1 = profile["pll1Settings"]
    pll2 = profile["pll2Settings"]
    out = profile["outputSettings"]
    sysref = profile["sysrefSettings"]

    # from no-OS/projects/ad9371/src/devices/ad9528/t_ad9528.h
    ref_buffer_ctrl = {
        "0": "DISABLED",
        "1": "SINGLE_ENDED",
        "2": "NEG_SINGLE_ENDED",
        "3": "DIFFERENTIAL",
    }

    output_driver_mode = {
        "0": "DRIVER_MODE_LVDS",
        "1": "DRIVER_MODE_LVDS_BOOST",
        "2": "DRIVER_MODE_HSTL",
    }
    output_signal_source = {
        "0": "SOURCE_VCO",
        "1": "SOURCE_VCXO",
        "2": "SOURCE_SYSREF_VCO",
        "3": "SOURCE_SYSREF_VCX",
        "5": "SOURCE_VCXO_INV",
        "7": "SOURCE_SYSREF_VCXO_IN",
    }

    sysref_request_method = {
        "0": "SYSREF_LEVEL_HIGH",
        "2": "SYSREF_EDGE_RISING",
        "3": "SYSREF_EDGE_FALLING",
    }
    sysref_source = {
        "0": "SYSREF_SRC_EXTERNAL",
        "1": "SYSREF_SRC_EXTERNAL_RESAMPLED",
        "2": "SYSREF_SRC_INTERNAL",
    }
    sysref_pattern_mode = {
        "0": "SYSREF_PATTERN_NSHOT",
        "1": "SYSREF_PATTERN_CONTINUOUS",
        "2": "SYSREF_PATTERN_PRBS",
        "3": "SYSREF_PATTERN_STOP",
    }
    sysref_nshot_mode = {
        "0": "SYSREF_NSHOT_1_PULSE", # FIXME: zero is undefined in AD9528 datasheet
        "1": "SYSREF_NSHOT_1_PULSE",
        "2": "SYSREF_NSHOT_2_PULSES",
        "3": "SYSREF_NSHOT_4_PULSES",
        "4": "SYSREF_NSHOT_6_PULSES",
        "5": "SYSREF_NSHOT_8_PULSES",
    }

    # bufferCtrl are used to set the following options but can't be edited in
    # - adi,ref[ab]-enable;
    # - adi,ref(a | b | osc-in)-diff-rcv-enable;
    # - adi,(a | b | osc-in)-cmos-neg-inp-enable;
    pll1["refA_bufferCtrl"] = ref_buffer_ctrl[pll1["refA_bufferCtrl"]]
    pll1["refB_bufferCtrl"] = ref_buffer_ctrl[pll1["refB_bufferCtrl"]]

    out["outPowerDown"] = f'0x{int(out["outPowerDown"]):x}'
    out["outSource"] = [output_signal_source[i] for i in out["outSource"].split()]
    out["outAnalogDelay"] = [int(i) for i in out["outAnalogDelay"].split()]
    out["outDigitalDelay"] = [int(i) for i in out["outDigitalDelay"].split()]
    out["outBufferCtrl"] = [output_driver_mode[i] for i in out["outBufferCtrl"].split()]
    out["outChannelDiv"] = [int(i) for i in out["outChannelDiv"].split()]
    out["outFrequency_Hz"] = [int(i) for i in out["outFrequency_Hz"].split()]

    sysref["sysrefRequestMethod"] = sysref["sysrefRequestMethod"] == '1' # enables GPIO SYSREF request otherwise SPI
    sysref["sysrefSource"] = sysref_source[sysref["sysrefSource"]]
    sysref['sysrefPinEdgeMode'] = sysref_request_method[sysref['sysrefPinEdgeMode']]
    del(sysref['sysrefPinBufferMode']) # SYSREF_REQ input buffer mode control not supported by kernel driver
    sysref["sysrefPatternMode"] = sysref_pattern_mode[sysref["sysrefPatternMode"]]
    sysref["sysrefNshotMode"] = sysref_nshot_mode[sysref["sysrefNshotMode"]]

    return {"pll1": pll1, "pll2": pll2, "out": out, "sysref": sysref}
