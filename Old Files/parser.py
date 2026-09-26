#parses the string from serial reader into a dictionary for easier use

def parse_packet(line):
    parts = line.split(',')
    if len(parts) != 5:
        return None
    
    try:
        return {
            "timestamp": int(parts[0]), #uint32_t type
            "sensor": parts[1],
            "value": float(parts[2]),
            "unit": parts[3],
            "status": parts[4]
        }
    except ValueError as e:
        return None
    