import xmltodict


def coefs_to_long_string(coefs):
    """Convert coefficient array to string.

    Args:
        coefs (list): Coefficients.

    Returns:
        str: Coefficients as a string.
    """
    result = ""
    for coef in coefs.split("\n"):
        coef = coef.replace(" ", "")
        result += f"({coef}) "
    return result[:-1]


def profile_to_xml(filename):
    # Update profile to non-shitty xml
    with open(filename) as sxmlfile:
        sxmldata = sxmlfile.read()
    # Correct each header
    outfile = []
    for line in sxmldata.split("\n"):
        if "<" in line and "</" not in line:
            within = line[line.find("<") + 1 : line.find(">")]
            # Fix all prop=val
            if "," in within:
                oline = []
                # print(line)
                for index, sline in enumerate(line.split(" ")):
                    if index == 3:
                        sline = f"Bandwidth={sline}"
                    if index in [4, 6]:
                        sline = sline + "="
                    oline += [sline]
                line = " ".join(oline)
                line = line.replace(",", "")
                line = line.replace("= ", "=")
            if " " in within:
                # print(line)
                oline = []
                spaces = 0
                for sline in line.split(" "):
                    if len(sline) > 0:
                        starter = sline + " "
                        break
                    spaces += 1
                for sline in line.split(" "):
                    if (
                        len(oline) == 0
                        and len(sline)
                        and "<" not in sline
                        and ">" not in sline
                        and "=" not in sline
                    ):
                        oline += [f'type="{sline}"']
                    if "=" in sline:
                        sline = sline.replace(">", "")
                        sline = sline.replace("<", "")
                        p = sline.split("=")[0]
                        v = sline.split("=")[1]
                        # print(f"{p}={v}")
                        oline += [f'{p}="{v}"']

                # print(" "*spaces+starter+" ".join(oline)+">")
                outfile += [" " * spaces + starter + " ".join(oline) + ">"]
            else:
                # print(line)
                if "=" in line:
                    s1 = line.find("<")
                    s2 = line.find(">")
                    within = line[s1 + 1 : s2]
                    o = within.split("=")
                    ss = f"{o[0]}>{o[1]}</{o[0]}"
                    line = line.replace(within, ss)
                # print(line)

                outfile += [line]
        else:
            outfile += [line]

    return "\n".join(outfile)
