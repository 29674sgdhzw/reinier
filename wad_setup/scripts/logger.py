import logging
import logging.handlers

def setup_logging(levelname, loggername, logfile_only):
    # create logger to log to screen and to file
    #logging.basicConfig(format='%(asctime)s [%(levelname)s:%(module)s:%(funcName)s]: %(message)s',level=level)
    loglevel = getattr(logging, levelname)
    logfile = '{}.log'.format(loggername)

    logger = logging.getLogger(loggername)
    logger.setLevel(loglevel)

    # restrict handlers to one of each only
    has_filehandler   = False
    has_streamhandler = False
    for hand in logger.handlers:
        if isinstance(hand, logging.FileHandler):
            has_filehandler = True
        elif isinstance(hand, logging.StreamHandler):
            has_streamhandler = True
            
    if not has_filehandler:
        formatter = logging.Formatter('%(asctime)s [%(levelname)s:%(module)s:%(funcName)s]: %(message)s')
        fh = logging.handlers.RotatingFileHandler(logfile, mode='a', maxBytes=2*1024*1024, backupCount=5) #append mode # max 6*2 MB
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    if not logfile_only and not has_streamhandler:
        formatter = logging.Formatter('[%(levelname)s]: %(message)s')
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)


