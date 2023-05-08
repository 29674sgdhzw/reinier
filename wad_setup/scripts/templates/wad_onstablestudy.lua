function OnStableStudy(studyId, tags, metadata)
   if (metadata['ModifiedFrom'] == nil and
       metadata['AnonymizedFrom'] == nil) then

      print('This study is now stable: ' .. studyId)
      
      -- Call WAD_Collector
      os.execute('__WADROOT__/orthanc/lua/wadselector.py --source WADQC --studyid ' .. studyId .. ' --inifile __WADROOT__/WAD_QC/wadconfig.ini --logfile_only')
      -- Alternatively, call WAD_Collector through wad_api (needs apt/yum installed lua-socket)
      -- local http = require'socket.http'
      -- body,c,l,h = http.request('http://127.0.0.1:3000/api/wadselector?studyid=' .. studyId .. '&source=WADQC')
   end
end
