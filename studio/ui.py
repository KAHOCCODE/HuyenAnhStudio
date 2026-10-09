from __future__ import annotations
import bisect, copy, json, os, sys, threading, uuid
from pathlib import Path
from shiboken6 import isValid
from PySide6.QtCore import Qt, Signal, QThread, QUrl, QRectF, QSizeF, QTimer, QAbstractTableModel, QModelIndex, QStandardPaths
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QFontMetricsF, QPainterPath, QPixmap, QTransform, QKeySequence, QShortcut, QDesktopServices, QImage
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,
    QFileDialog,QMessageBox,QSplitter,QScrollArea,QFormLayout,QDoubleSpinBox,QSpinBox,QComboBox,QCheckBox,QLineEdit,
    QTextEdit,QTableView,QAbstractItemView,QHeaderView,QSlider,QProgressBar,QPlainTextEdit,QGraphicsView,QGraphicsScene,
    QGraphicsObject,QFrame,QColorDialog,QFontComboBox,QScrollBar,QGroupBox,QSizePolicy,QDialog,QGraphicsPixmapItem,QTableWidget,QTableWidgetItem,QMenu,QDockWidget,QInputDialog,QGraphicsRectItem)
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput,QVideoSink,QMediaDevices

from .core import *
from .effects_ui import EffectsDialog

VOICES={'Nam Minh · Nam':'vi-VN-NamMinhNeural','Hoài My · Nữ':'vi-VN-HoaiMyNeural'}

class ElidedLabel(QLabel):
    """One line, responsive width; keep the complete value in a tooltip."""
    def __init__(self,text='',parent=None):
        super().__init__(parent);self._full=text
        self.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
        self.setMinimumWidth(0);self.setText(text)
    def setText(self,text):
        self._full=text;self.setToolTip(text);self._refresh()
    def _refresh(self):
        super().setText(self.fontMetrics().elidedText(self._full,Qt.ElideMiddle,max(0,self.contentsRect().width())))
    def resizeEvent(self,event):
        super().resizeEvent(event);self._refresh()

class CPUFrames:
    """Bounded, cancellable decoder. No encoded proxy and no frame signals accumulating in Qt."""
    def __init__(self, path, codec, width, height, start, origin=0):
        import queue
        self.frames=queue.Queue(maxsize=8);self.cancel=threading.Event()
        self.proc=None;self.error='';self.done=False;self.start_time=start;self.origin=origin
        scale=min(1,960/max(1,width),540/max(1,height))
        self.width=max(2,int(width*scale)//2*2);self.height=max(2,int(height*scale)//2*2)
        self.thread=threading.Thread(target=self.decode,args=(path,codec,start),daemon=True)
        self.thread.start()
    def decode(self,path,codec,start):
        import queue,tempfile
        try:
            args=[binary('ffmpeg'),'-hide_banner','-loglevel','error','-nostdin']+software_decode_args(codec)
            args+=['-ss',f'{start:.6f}','-i',path,'-map','0:v:0','-an','-sn','-dn',
                   '-vf',f'setpts=PTS-STARTPTS,fps=30,scale={self.width}:{self.height}:flags=fast_bilinear',
                   '-pix_fmt','rgb24','-f','rawvideo','pipe:1']
            if self.cancel.is_set():return
            with tempfile.TemporaryFile() as errors:
                self.proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=errors,stdin=subprocess.DEVNULL,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if self.cancel.is_set():self.proc.kill()
                length=self.width*self.height*3;index=0
                while not self.cancel.is_set():
                    parts=[];remaining=length
                    while remaining and not self.cancel.is_set():
                        part=self.proc.stdout.read(remaining)
                        if not part:break
                        parts.append(part);remaining-=len(part)
                    if remaining:break
                    frame=(self.origin+start+index/30,b''.join(parts));index+=1
                    while not self.cancel.is_set():
                        try:self.frames.put(frame,timeout=.05);break
                        except queue.Full:pass
                if self.cancel.is_set() and self.proc.poll() is None:self.proc.kill()
                code=self.proc.wait()
                if code and not self.cancel.is_set():
                    errors.seek(max(0,errors.tell()-6000));self.error=errors.read().decode('utf-8',errors='replace')
                if not index and not self.cancel.is_set() and not self.error:self.error='Không giải mã được khung hình tại vị trí này.'
        except Exception as e:
            if not self.cancel.is_set():self.error=str(e)
        finally:
            if self.proc:
                if self.proc.poll() is None:self.proc.kill();self.proc.wait()
                if self.proc.stdout:self.proc.stdout.close()
            self.done=True
    def close(self):
        self.cancel.set()
        if self.proc and self.proc.poll() is None:
            try:self.proc.kill()
            except OSError:pass

class Worker(QThread):
    progress=Signal(float,str); result=Signal(object); failed=Signal(str)
    def __init__(self,fn): super().__init__(); self.fn=fn;self.cancel=threading.Event()
    def run(self):
        try: self.result.emit(self.fn(self.cancel,self.progress.emit))
        except Exception as e: self.failed.emit(str(e))

class CueModel(QAbstractTableModel):
    def __init__(self,window): super().__init__();self.win=window;self.indices=[];self.query='';self.only_long=False
    def refresh(self):
        self.beginResetModel()
        self.indices=[i for i,c in enumerate(self.win.p.cues) if (not self.query or self.query.casefold() in c.text.casefold()) and (not self.only_long or self.win.row_status(c)[0]=='long')]
        self.endResetModel()
    def rowCount(self,parent=QModelIndex()): return len(self.indices)
    def columnCount(self,parent=QModelIndex()): return 3
    def headerData(self,section,orientation,role):
        if role==Qt.DisplayRole and orientation==Qt.Horizontal: return ['# / Mốc gốc','Phụ đề tiếng Việt','Voice'][section]
    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid(): return
        i=self.indices[index.row()];c=self.win.p.cues[i];status,label=self.win.row_status(c)
        if role==Qt.DisplayRole: return [f'{i+1} · {stamp(c.start)}',c.text.replace('\n',' ') or '— Mục trống —',label][index.column()]
        if role==Qt.ToolTipRole: return f'{stamp(c.start)} → {stamp(c.end)}\n{c.text}\n{label}'
        if role==Qt.ForegroundRole:
            return QColor('#ffb9a1' if status=='long' else '#83929e' if not plain(c.text) else '#d7e1e9')

class Overlay(QGraphicsObject):
    moved=Signal(); before_drag=Signal()
    def __init__(self,win):
        super().__init__();self.win=win;self.frame=QImage();self.text='';self.drag=None;self.text_rect=QRectF()
        self.setZValue(10);self.setAcceptedMouseButtons(Qt.LeftButton)
    def boundingRect(self): return QRectF(0,0,self.win.p.width,self.win.p.height)
    def mask_rect(self):
        p=self.win.p;m=p.mask
        return QRectF(m['x']*p.width/100,m['y']*p.height/100,m['w']*p.width/100,m['h']*p.height/100)
    def paint(self,painter,option,widget=None):
        p=self.win.p;st=p.style;m=p.mask
        painter.setRenderHint(QPainter.Antialiasing)
        if m['enabled']:
            r=self.mask_rect()
            if m['mode']=='blur' and not self.frame.isNull():
                src=QRectF(r.x()*self.frame.width()/p.width,r.y()*self.frame.height()/p.height,r.width()*self.frame.width()/p.width,r.height()*self.frame.height()/p.height).toRect()
                patch=self.frame.copy(src).scaled(max(2,int(r.width()/28)),max(2,int(r.height()/28)),Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                painter.setRenderHint(QPainter.SmoothPixmapTransform);painter.drawImage(r,patch)
            else:
                color=QColor(m['color']);color.setAlphaF(m['opacity']);painter.fillRect(r,color)
            if self.win.mask_edit.isChecked():
                painter.setPen(QPen(QColor('#ffb36b'),max(2,p.width/640),Qt.DashLine));painter.drawRect(r)
                painter.fillRect(QRectF(r.right()-18,r.bottom()-18,18,18),QColor('#ffb36b'))
        self.paint_screen_regions(painter)
        if not self.text: self.text_rect=QRectF();return
        f=QFont(st['font']);f.setPixelSize(max(8,round(st['size']*p.height/1080)));f.setBold(st['bold'])
        fm=QFontMetricsF(f);maxwidth=p.width*st['width']/100;lines=[]
        for paragraph in plain(self.text).split('\n'):
            current=''
            for word in paragraph.split():
                test=(current+' '+word).strip()
                if current and fm.horizontalAdvance(test)>maxwidth: lines.append(current);current=word
                else: current=test
            lines.append(current)
        lineh=fm.height();cx=p.width*st['x']/100;bottom=p.height*st['y']/100
        top=bottom-lineh*len(lines);path=QPainterPath()
        for i,line in enumerate(lines): path.addText(cx-fm.horizontalAdvance(line)/2,top+fm.ascent()+i*lineh,f,line)
        self.text_rect=path.boundingRect().adjusted(-12,-12,12,12)
        if st['box']: painter.fillRect(self.text_rect,QColor(0,0,0,190))
        if st['shadow']:
            painter.save();painter.translate(st['shadow']*p.height/1080,st['shadow']*p.height/1080);painter.fillPath(path,QColor(0,0,0,190));painter.restore()
        if st['outline']:
            painter.setPen(QPen(QColor('black'),2*st['outline']*p.height/1080,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));painter.drawPath(path)
        painter.fillPath(path,QColor(st['color']))
    def paint_screen_regions(self,painter):
        p=self.win.p;t=getattr(self.win,'_screen_time',0)
        for r in p.screen_regions:
            if not r.get('enabled',True) or not r['start']<=t<r['end']:continue
            rect=QRectF(*region_pixels(p,r))
            if r['mode']=='blur' and not self.frame.isNull():
                src=QRectF(rect.x()*self.frame.width()/p.width,rect.y()*self.frame.height()/p.height,rect.width()*self.frame.width()/p.width,rect.height()*self.frame.height()/p.height).toRect()
                divisor=max(2,r['strength']);patch=self.frame.copy(src).scaled(max(2,int(src.width()/divisor)),max(2,int(src.height()/divisor)),Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                painter.setRenderHint(QPainter.SmoothPixmapTransform);painter.drawImage(rect,patch)
            elif r['mode']=='solid':painter.fillRect(rect,QColor('#171717'))
            if not r['text']:continue
            font=QFont(p.style['font']);font.setPixelSize(max(8,round(r['size']*p.height/1080)));font.setBold(True);fm=QFontMetricsF(font);lines=[]
            for paragraph in plain(r['text']).split('\n'):
                current=''
                for word in paragraph.split():
                    test=(current+' '+word).strip()
                    if current and fm.horizontalAdvance(test)>rect.width():lines.append(current);current=word
                    else:current=test
                lines.append(current)
            path=QPainterPath();top=rect.center().y()-fm.height()*len(lines)/2
            for i,line in enumerate(lines):path.addText(rect.center().x()-fm.horizontalAdvance(line)/2,top+fm.ascent()+i*fm.height(),font,line)
            painter.setPen(QPen(QColor('black'),6*p.height/1080,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));painter.drawPath(path);painter.fillPath(path,QColor(r['color']))

    def mousePressEvent(self,event):
        if self.win.busy: return
        self.before_drag.emit();pos=event.pos();m=self.win.p.mask
        if self.win.mask_edit.isChecked() and m['enabled']:
            r=self.mask_rect()
            self.drag='resize' if abs(pos.x()-r.right())<40 and abs(pos.y()-r.bottom())<40 else 'mask'
            self.origin=pos;self.original=copy.deepcopy(m)
        elif self.text_rect.contains(pos):
            self.drag='text';self.origin=pos;self.original=copy.deepcopy(self.win.p.style)
        event.accept()
    def mouseMoveEvent(self,event):
        if not self.drag:return
        p=self.win.p;dx=(event.pos().x()-self.origin.x())/p.width*100;dy=(event.pos().y()-self.origin.y())/p.height*100;o=self.original
        if self.drag=='text': p.style['x']=max(0,min(100,o['x']+dx));p.style['y']=max(0,min(100,o['y']+dy))
        elif self.drag=='mask': p.mask['x']=max(0,min(100-o['w'],o['x']+dx));p.mask['y']=max(0,min(100-o['h'],o['y']+dy))
        else: p.mask['w']=max(1,min(100-o['x'],o['w']+dx));p.mask['h']=max(1,min(100-o['y'],o['h']+dy))
        self.update();self.moved.emit()
    def mouseReleaseEvent(self,event):
        if self.drag:self.win.changed(refresh=False)
        self.drag=None

class Preview(QGraphicsView):
    def __init__(self,win):
        super().__init__();self.win=win;self.setScene(QGraphicsScene(self));self.setBackgroundBrush(QColor('#090c11'))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.video=QGraphicsPixmapItem();self.video.setTransformationMode(Qt.SmoothTransformation);self.scene().addItem(self.video);self.overlay=Overlay(win);self.scene().addItem(self.overlay)
        self.pick_origin=None;self.pick_box=QGraphicsRectItem();self.pick_box.setZValue(30);self.pick_box.setPen(QPen(QColor('#73dfcc'),3));self.pick_box.setBrush(QColor(70,200,180,40));self.scene().addItem(self.pick_box);self.pick_box.hide()
        self.setMinimumSize(300,160);self.setViewport(QWidget());self.reset_size()
    def reset_size(self):
        self.overlay.prepareGeometryChange();self.video.setPixmap(QPixmap());self.overlay.frame=QImage()
        self.setSceneRect(0,0,self.win.p.width,self.win.p.height);self.fitInView(self.sceneRect(),Qt.KeepAspectRatio)
    def show_frame(self,frame):
        image=frame if isinstance(frame,QImage) else frame.toImage()
        if image.isNull():return False
        # Paint decoded CPU pixels in a regular QWidget, avoiding a separate GPU video surface.
        self.video.setPixmap(QPixmap.fromImage(image))
        self.video.setTransform(QTransform.fromScale(self.win.p.width/image.width(),self.win.p.height/image.height()))
        self.overlay.frame=image;self.overlay.update()
        return True
    def mousePressEvent(self,event):
        if getattr(self.win,'region_select',None) and self.win.region_select.isChecked() and event.button()==Qt.LeftButton:
            if self.win.busy or self.overlay.frame.isNull():return
            pos=self.mapToScene(event.position().toPoint())
            if not self.sceneRect().contains(pos):return
            self.pick_origin=pos;self.pick_box.setRect(QRectF(pos,pos));self.pick_box.show();event.accept();return
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.pick_origin is not None:
            rect=QRectF(self.pick_origin,self.mapToScene(event.position().toPoint())).normalized().intersected(self.sceneRect());self.pick_box.setRect(rect);event.accept();return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        if self.pick_origin is not None:
            rect=self.pick_box.rect();self.pick_origin=None;self.pick_box.hide();self.win.region_select.setChecked(False)
            if rect.width()>4 and rect.height()>4:QTimer.singleShot(0,lambda r=QRectF(rect):self.win.new_screen_region(r))
            event.accept();return
        super().mouseReleaseEvent(event)
    def resizeEvent(self,e): super().resizeEvent(e);self.fitInView(self.sceneRect(),Qt.KeepAspectRatio)

class Timeline(QWidget):
    seek=Signal(float);chosen=Signal(str)
    def __init__(self,win):
        super().__init__();self.win=win;self.zoom=70.;self.offset=0.;self.cursor=0.;self.drag=None;self.selected_ids=set();self.setFocusPolicy(Qt.StrongFocus);self.setMinimumHeight(132);self.setMouseTracking(True)
    def x(self,t):return 108+(t/1-self.offset)*self.zoom
    def source(self,x):return max(0,(self.offset+(x-108)/self.zoom))
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#10151d'));p.setRenderHint(QPainter.Antialiasing)
        rows=[('VIDEO',28,'#406991'),('PHỤ ĐỀ',60,'#289c91'),('VOICE',92,'#8260be')]
        p.setFont(QFont('Segoe UI',9))
        for label,y,color in rows:
            p.fillRect(0,y,108,28,QColor('#19212c'));p.setPen(QColor('#aebdcc'));p.drawText(12,y+20,label)
            p.setPen(QColor('#232d3a'));p.drawLine(108,y+28,self.width(),y+28)
        p.save();p.setClipRect(108,0,self.width()-108,self.height())
        duration=self.win.p.duration
        step=next((s for s in [.1,.2,.5,1,2,5,10,20,30,60,120,300,600,1800] if s*self.zoom>=70),3600)
        t=int(self.offset/step)*step
        while t<self.offset+(self.width()-108)/self.zoom:
            x=108+(t-self.offset)*self.zoom;p.setPen(QColor('#263240'));p.drawLine(int(x),25,int(x),self.height());p.setPen(QColor('#90a3b6'));p.drawText(int(x)+4,19,(stamp(t)[3:-1] if step<1 else stamp(t)[:-4]));t+=step
        r=QRectF(self.x(0),31,duration*self.zoom,24);p.fillRect(r,QColor('#305271'));p.setPen(QColor('#d4e7f7'));p.drawText(r.adjusted(10,0,0,0),Qt.AlignVCenter,Path(self.win.p.video).name or 'Chọn video để bắt đầu')
        if self.win._batch_segment:
            a,b=self.win._batch_segment
            p.fillRect(QRectF(self.x(a),28,(b-a)*self.zoom,96),QColor(76,137,199,28))
            p.setPen(QPen(QColor('#679fc8'),1,Qt.DashLine))
            for bound in (a,b):p.drawLine(int(self.x(bound)),25,int(self.x(bound)),124)
        lo=self.source(108);hi=self.source(self.width())
        for c in self.win.p.cues:
            if c.start>hi:continue
            voice_end=self.voice_end(c)
            if voice_end<lo:continue
            status,_=self.win.row_status(c);row=self.win.rows.get(c.id)
            if row and status in ('ready','cached','long'):
                required=max(1,row['duration']/((c.end-c.start)/self.win.p.work_speed))
                voice_end=max(c.end,c.start+row['duration']/min(required,self.win.p.max_fit)*self.win.p.work_speed)
            if voice_end<lo:continue
            if c.start>hi:continue
            x=self.x(c.start);w=max(2,(c.end-c.start)*self.zoom)
            for y,color in [(63,'#226b68'),(95,'#9f5b4a' if status=='long' else '#6d509a' if status in ('ready','cached') else '#303643')]:
                block_width=max(2,(voice_end-c.start)*self.zoom) if y==95 else w
                rect=QRectF(x,y,block_width,24);p.setPen(QPen(QColor('#f1c885') if c.id in self.selected_ids else QColor(color),2));p.setBrush(QColor(color));p.drawRoundedRect(rect,3,3)
                if w>30:
                    p.setPen(QColor('#e6f0f5'));p.drawText(rect.adjusted(5,0,-4,0),Qt.AlignVCenter,QFontMetricsF(p.font()).elidedText(plain(c.text) or 'Trống',Qt.ElideRight,int(w-9)))
        if self.win.selection:
            a,b=self.win.selection;r=QRectF(self.x(a),25,(b-a)*self.zoom,99)
            p.fillRect(r,QColor(115,190,255,45));p.setPen(QPen(QColor('#83cfff'),2));p.setBrush(Qt.NoBrush);p.drawRect(r)
        x=self.x(self.cursor);p.setPen(QPen(QColor('#fae0a2'),2));p.drawLine(int(x),23,int(x),self.height());p.restore()
    def choose(self,ids,primary=None):
        if self.win.editor_dirty and not self.win.commit_editor():return
        ids=set(ids)&{c.id for c in self.win.p.cues}
        primary=primary if primary in ids else next((c.id for c in self.win.p.cues if c.id in ids),None)
        self.win.select_id(primary);self.selected_ids=ids
        self.win.timeline_selection_label.setText(f'{len(ids)} câu chọn');self.update()
    def voice_end(self,c):
        row=self.win.rows.get(c.id)
        if row and str(self.win.cache/(raw_key(c,self.win.p)+'.mp3'))==row.get('raw'):
            factor=max(1,row['duration']/((c.end-c.start)/self.win.p.work_speed))
            return max(c.end,c.start+row['duration']/min(factor,self.win.p.max_fit)*self.win.p.work_speed)
        return c.end
    def hit(self,t,y):
        if not 60<=y<=123:return None
        return next((c for c in reversed(self.win.p.cues) if c.start<=t<=(self.voice_end(c) if y>=92 else c.end)),None)
    def targets(self,exclude):
        points=[0.,self.win.p.duration,self.cursor]
        for c in self.win.p.cues:
            if c.id not in exclude:points.extend((c.start,c.end))
        if self.win.selection:points.extend(self.win.selection)
        if self.win._batch_segment:points.extend(self.win._batch_segment)
        return points
    def finalize(self):
        ids=set(self.selected_ids);primary=self.win.selected
        self.win.p.cues.sort(key=lambda c:c.start);self.win.changed();self.choose(ids,primary)
        self.win.status.setText('Đã chỉnh mốc nhóm câu. MP3 được giữ; voice sẽ ghép lại theo mốc mới khi nghe.')
    def shift_selected(self,delta):
        if not self.win.guard():return
        if self.win.editor_dirty and not self.win.commit_editor():return
        snapshot={c.id:(c.start,c.end) for c in self.win.p.cues if c.id in self.selected_ids}
        moved=timeline_move(snapshot,delta,self.win.p.duration)
        if moved==snapshot:return
        self.win.player.pause();self.win.push_undo()
        for c in self.win.p.cues:
            if c.id in moved:c.start,c.end=moved[c.id]
        self.finalize()
    def delete_selected(self):
        if not self.selected_ids or not self.win.guard():return
        self.win.player.pause();self.win.push_undo();self.win.editor_dirty=False
        self.win.p.cues=[c for c in self.win.p.cues if c.id not in self.selected_ids]
        self.choose([]);self.win.changed()
    def select_region_cues(self):
        if self.win.selection:
            a,b=self.win.selection;self.choose([c.id for c in self.win.p.cues if c.start<b and c.end>a])
    def mousePressEvent(self,event):
        if self.win.busy or event.button() not in (Qt.LeftButton,Qt.MiddleButton):return
        if self.win.editor_dirty and not self.win.commit_editor():return
        self.setFocus(Qt.MouseFocusReason)
        x=event.position().x();y=event.position().y()
        if x<108:return
        t=min(self.win.p.duration,self.source(x))
        if event.button()==Qt.MiddleButton:
            self.drag=dict(mode='pan',x=x,offset=self.offset,clicked=t,middle=True,moved=False);self.setCursor(Qt.ClosedHandCursor);return
        if self.win.select_region.isChecked() or event.modifiers()&Qt.ShiftModifier:
            self.drag=dict(mode='region',origin=t);self.win.set_region(t,min(self.win.p.duration,t+.04));return
        cue=self.hit(t,y)
        if cue:
            if event.modifiers()&Qt.ControlModifier:
                ids=self.selected_ids^{cue.id};self.choose(ids,cue.id);return
            ids=self.selected_ids if cue.id in self.selected_ids else {cue.id}
            self.choose(ids,cue.id);self.win.player.pause()
            # The voice follows the subtitle timing. Its spill area can be selected and moved.
            mode='left' if abs(x-self.x(cue.start))<7 else 'right' if y<92 and abs(x-self.x(cue.end))<7 else 'move'
            if mode!='move':self.choose({cue.id},cue.id)
            snapshot={c.id:(c.start,c.end) for c in self.win.p.cues if c.id in self.selected_ids}
            self.drag=dict(mode=mode,origin=t,id=cue.id,snapshot=snapshot,undo=False,targets=self.targets(self.selected_ids));return
        if y>=28:
            self.drag=dict(mode='pan',x=x,offset=self.offset,clicked=t,middle=False,moved=False);self.setCursor(Qt.ClosedHandCursor)
        else:self.seek.emit(t);self.drag=dict(mode='seek')
    def mouseMoveEvent(self,event):
        t=min(self.win.p.duration,self.source(event.position().x()))
        if not self.drag:
            cue=self.hit(t,event.position().y())
            if cue:
                status=self.win.row_status(cue)[1]
                self.setToolTip(f'{stamp(cue.start)} → {stamp(cue.end)}\n{plain(cue.text)}\nVoice: {status}\nCtrl + bấm: chọn nhiều · Alt + ←/→: dịch 1/30 giây')
            else:self.setToolTip('Kéo hàng video/khoảng trống để cuộn · Chuột giữa kéo mọi nơi · Kéo thước để tua · Shift + kéo: chọn vùng · I/O: đầu/cuối vùng · F: vừa vùng/lô')
            return
        d=self.drag
        if d['mode']=='pan':
            delta=event.position().x()-d['x'];d['moved']=d['moved'] or abs(delta)>3
            self.win.scroll.setValue(round(max(0,d['offset']-delta/self.zoom)*100));return
        if d['mode']=='region':self.win.set_region(min(t,d['origin']),max(t,d['origin']));return
        if d['mode']=='seek':self.seek.emit(t);return
        delta=t-d['origin'];snapshot=d['snapshot'];a,b=snapshot[d['id']]
        snap=self.win.timeline_snap.isChecked() and not event.modifiers()&Qt.AltModifier
        tolerance=min(.2,8/self.zoom)
        if d['mode']=='move':
            if snap:
                corrections=[timeline_snap(v+delta,d['targets'],tolerance)-(v+delta) for v in (a,b)]
                corrections=[v for v in corrections if abs(v)>1e-9]
                if corrections:delta+=min(corrections,key=abs)
            changed=timeline_move(snapshot,delta,self.win.p.duration)
        elif d['mode']=='left':
            value=timeline_snap(a+delta,d['targets'],tolerance) if snap else a+delta
            changed={d['id']:(round(max(0,min(b-.04,value)),3),b)}
        else:
            value=timeline_snap(b+delta,d['targets'],tolerance) if snap else b+delta
            changed={d['id']:(a,round(max(a+.04,min(self.win.p.duration,value)),3))}
        if changed!=snapshot and not d['undo']:self.win.push_undo();d['undo']=True
        for c in self.win.p.cues:
            if c.id in changed:c.start,c.end=changed[c.id]
        self.update()
    def mouseReleaseEvent(self,event):
        d=self.drag;self.drag=None;self.unsetCursor()
        if d and d.get('undo'):self.finalize()
        elif d and d['mode']=='pan':
            if not d['moved'] and not d['middle']:self.seek.emit(d['clicked'])
        elif d and 'id' in d:self.win.navigate_cue(d['id'],preserve_selection=True)
    def mouseDoubleClickEvent(self,event):
        if self.win.busy:return
        cue=self.hit(self.source(event.position().x()),event.position().y())
        if cue:self.win.navigate_cue(cue.id);self.win.show_editor()
    def wheelEvent(self,event):
        if event.modifiers()&Qt.ControlModifier:
            x=max(108,event.position().x());anchor=self.source(x)
            self.zoom=max(.005,min(10000,self.zoom*(1.35 if event.angleDelta().y()>0 else 1/1.35)))
            self.win.zoom.blockSignals(True);self.win.zoom.setValue(round((math.log10(self.zoom)+.1)/.035));self.win.zoom.blockSignals(False);self.win.update_scroll()
            self.win.scroll.setValue(round(max(0,anchor-(x-108)/self.zoom)*100))
        else:
            step=max(.1,(self.width()-108)/self.zoom*.15)
            self.win.scroll.setValue(self.win.scroll.value()-round(event.angleDelta().y()/120*step*100))
        event.accept()
    def keyPressEvent(self,event):
        if self.win.busy:return
        key=event.key();mods=event.modifiers()
        if key==Qt.Key_Space:self.win.toggle_play()
        elif key==Qt.Key_Delete:self.delete_selected()
        elif key==Qt.Key_A and mods&Qt.ControlModifier:self.choose([c.id for c in self.win.p.cues])
        elif key==Qt.Key_Escape:self.choose([]);self.win.clear_region()
        elif key in (Qt.Key_Left,Qt.Key_Right):
            step=(.1 if mods&Qt.ShiftModifier else 1/30)*(1 if key==Qt.Key_Right else -1)
            if mods&Qt.AltModifier:self.shift_selected(step)
            else:self.win.seek(self.cursor+step)
        elif key==Qt.Key_I:self.win.set_region(self.cursor,max(self.cursor+.04,self.win.selection[1] if self.win.selection else self.win.p.duration))
        elif key==Qt.Key_O:self.win.set_region(min(self.cursor-.04,self.win.selection[0] if self.win.selection else 0),self.cursor)
        elif key==Qt.Key_F:self.win.fit_timeline_scope()
        elif key==Qt.Key_Home:self.win.seek(self.win.review_start())
        elif key==Qt.Key_End:self.win.seek(self.win._preview_end if self.win._preview_end is not None else self.win.p.duration)
        else:super().keyPressEvent(event);return
        event.accept()
    def contextMenuEvent(self,event):
        if self.win.busy:return
        self.setFocus(Qt.MouseFocusReason)
        cue=self.hit(self.source(event.pos().x()),event.pos().y())
        if cue and cue.id not in self.selected_ids:self.choose({cue.id},cue.id)
        menu=QMenu(self)
        edit=menu.addAction('Sửa câu đang chọn…',self.win.show_editor);edit.setEnabled(bool(self.selected_ids))
        menu.addAction('Chọn tất cả câu',lambda:self.choose([c.id for c in self.win.p.cues]))
        region=menu.addAction('Chọn các câu trong vùng',self.select_region_cues);region.setEnabled(bool(self.win.selection))
        menu.addSeparator()
        for label,fn in [('Dịch nhóm trái 0,1 giây',lambda:self.shift_selected(-.1)),('Dịch nhóm phải 0,1 giây',lambda:self.shift_selected(.1)),('Xóa các câu đã chọn',self.delete_selected)]:
            action=menu.addAction(label,fn);action.setEnabled(bool(self.selected_ids))
        menu.addSeparator();menu.addAction('Vừa vùng / lô đang rà',self.win.fit_timeline_scope)
        menu.exec(event.globalPos())


class Window(QMainWindow):
    def __init__(self):
        super().__init__();self.p=Project();self.project_path=None;self.selected=None;self.busy=False;self.dirty=False;self.undo=[];self.redo=[];self.worker=None;self.rows={};self.syncing=False;self.editor_dirty=False;self.editor_loading=False;self.selection=None;self.range_play_end=None
        root=Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation));self.cache_root=root/'cache';self.cache_id=uuid.uuid4().hex;self.cache=self.cache_root/self.cache_id;self.cache.mkdir(parents=True,exist_ok=True)
        self.setWindowTitle('HUYỄN ẢNH Studio · Phụ đề & Lồng tiếng');self.resize(1320,720);self.setMinimumSize(1080,650)
        self.player=QMediaPlayer(self);self.audio=QAudioOutput(self);self.player.setAudioOutput(self.audio)
        self.voice_player=QMediaPlayer(self);self.voice_audio=QAudioOutput(self);self.voice_player.setAudioOutput(self.voice_audio)
        self.sample_player=QMediaPlayer(self);self.sample_audio=QAudioOutput(self);self.sample_player.setAudioOutput(self.sample_audio)
        self._preview_offset_ms=0;self._preview_end=None;self._batch_segment=None;self._voice_offset_ms=0;self._load_batch_resume=None
        self.cpu_mode=False;self.cpu_decoder=None;self.cpu_pending=None;self._cpu_seek_target=0
        self.build();self.video_sink=QVideoSink(self);self.player.setVideoSink(self.video_sink);self.frame_count=0
        self.player.positionChanged.connect(lambda ms:self.on_position(round(self.preview_clock()*1000) if self.cpu_mode else ms+self._preview_offset_ms));self.player.playbackStateChanged.connect(self.play_state)
        self.player.errorOccurred.connect(self.preview_error)
        self.video_sink.videoFrameChanged.connect(self.on_frame)
        self.player.mediaStatusChanged.connect(self.preview_media_status)
        self.player.tracksChanged.connect(self.preview_tracks_changed)
        self.voice_player.mediaStatusChanged.connect(lambda status:self.sync_voice(force=True) if status==QMediaPlayer.LoadedMedia else None)
        self.cpu_timer=QTimer(self);self.cpu_timer.timeout.connect(self.present_cpu);self.cpu_timer.start(16)
        self.cpu_seek_timer=QTimer(self);self.cpu_seek_timer.setSingleShot(True);self.cpu_seek_timer.timeout.connect(self.start_cpu_decoder)
        self.preview.overlay.moved.connect(self.pull_visual_controls);self.preview.overlay.before_drag.connect(self.push_undo)
        self.timer=QTimer(self);self.timer.timeout.connect(self.sync_voice);self.timer.start(300)
        for seq,fn in [('Ctrl+S',self.save),('Ctrl+Shift+S',lambda:self.save(save_as=True)),('Ctrl+O',self.open_project),('Ctrl+Z',self.undo_action),('Ctrl+Y',self.redo_action),('F11',self.fullscreen),('Ctrl+R',lambda:self.sync_voice(force=True))]:QShortcut(QKeySequence(seq),self,activated=fn)
        self.load_controls();self.changed(refresh=True,dirty=False);self.dirty=False
        for widget in [self.start,self.end]:widget.textEdited.connect(self.editor_changed)
        self.text.textChanged.connect(self.editor_changed);self.cue_voice.currentIndexChanged.connect(self.editor_changed);self.cue_rate.valueChanged.connect(self.editor_changed)
        self.log('Sẵn sàng. Chọn video → Nhập SRT → Chỉnh chữ / vùng che → Tạo voice → Xuất video.')
    def button(self,text,fn,primary=False):
        b=QPushButton(text);b.clicked.connect(fn)
        if primary:b.setObjectName('primary')
        return b
    def build(self):
        base=QWidget();self.setCentralWidget(base);outer=QVBoxLayout(base);outer.setContentsMargins(14,12,14,10);outer.setSpacing(10)
        head=QHBoxLayout();brand=QLabel('HUYỄN ẢNH  /  STUDIO');brand.setObjectName('brand');head.addWidget(brand);head.addStretch()
        for text,fn in [('Dự án mới',self.new_project),('Mở dự án',self.open_project),('Lưu',self.save),('Hoàn tác',self.undo_action),('Toàn màn hình',self.fullscreen)]:
            button=self.button(text,fn)
            if text=='Lưu':
                button.clicked.disconnect()
                button.setText('Lưu ▾');menu=QMenu(button);menu.addAction('Lưu dự án  ·  Ctrl+S',self.save);menu.addAction('Lưu thành…  ·  Ctrl+Shift+S',lambda:self.save(save_as=True));button.setMenu(menu)
            head.addWidget(button)
        self.export_btn=self.button('Xuất video',self.export,True);head.addWidget(self.export_btn);outer.addLayout(head)
        self.split=QSplitter(Qt.Horizontal);outer.addWidget(self.split,1)
        left=QWidget();ll=QVBoxLayout(left);ll.setContentsMargins(0,0,0,0);ll.setSpacing(4)
        source=QHBoxLayout();source.setSpacing(4);source.addWidget(QLabel('NGUỒN & SUB'),1)
        for title,fn in [('＋ Video',self.import_video),('＋ SRT',self.import_srt)]:
            button=self.button(title,fn);button.setStyleSheet('padding: 4px 8px;');source.addWidget(button)
        ll.addLayout(source)
        self.media_label=ElidedLabel('Chưa chọn video');self.media_label.setObjectName('muted');ll.addWidget(self.media_label)
        self.media_details=ElidedLabel();self.media_details.setObjectName('muted');ll.addWidget(self.media_details)
        self.search=QLineEdit();self.search.setPlaceholderText('Tìm nội dung phụ đề…');self.search.textChanged.connect(self.filter_rows);ll.addWidget(self.search)
        self.voice_summary=ElidedLabel('Voice: chưa tạo');self.voice_summary.setObjectName('muted');ll.addWidget(self.voice_summary)
        self.long_only=QCheckBox('Chỉ hiện câu voice quá dài');self.long_only.toggled.connect(self.filter_rows);ll.addWidget(self.long_only)
        self.table=QTableView();self.model=CueModel(self);self.table.setModel(self.model);self.table.setSelectionBehavior(QAbstractItemView.SelectRows);self.table.setSelectionMode(QAbstractItemView.SingleSelection);self.table.setWordWrap(False);self.table.verticalHeader().hide();self.table.verticalHeader().setDefaultSectionSize(35);self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch);self.table.setColumnWidth(0,120);self.table.setColumnWidth(2,78);self.table.clicked.connect(self.table_clicked);self.table.doubleClicked.connect(lambda index:self.show_editor());ll.addWidget(self.table,1)
        row=QHBoxLayout()
        for text,fn in [('+ Câu',self.add_cue),('Xóa câu',self.delete_cue),('Lưu SRT',self.save_srt)]:row.addWidget(self.button(text,fn))
        ll.addLayout(row);ll.addWidget(self.button('Xóa toàn bộ SRT',self.remove_srt));left.setMinimumWidth(300);self.split.addWidget(left)
        center=QWidget();cl=QVBoxLayout(center);cl.setContentsMargins(0,0,0,0)
        title=QHBoxLayout();title.addWidget(QLabel('02  KHUNG XEM TRƯỚC'));title.addStretch();self.focus_button=self.button('Phóng video',self.focus_preview);title.addWidget(self.focus_button);self.preview_mode=QComboBox();self.preview_mode.addItems(['Theo tốc độ dựng','Theo tốc độ bản cuối']);self.preview_mode.currentIndexChanged.connect(self.update_rates);self.preview_mode.setMaximumWidth(170);title.addWidget(self.preview_mode);cl.addLayout(title)
        self.mask_edit=QCheckBox('Kéo vùng che');self.preview=Preview(self);cl.addWidget(self.preview,1)
        region_tools=QHBoxLayout();self.region_select=QCheckBox('Kéo chọn vùng chữ / watermark');self.region_select.toggled.connect(self.toggle_screen_selection);region_tools.addWidget(self.region_select);region_tools.addWidget(self.button('Các vùng chữ / làm mờ…',self.manage_screen_regions));cl.addLayout(region_tools)
        self.empty_hint=QLabel('Kéo chữ để đặt vị trí • Nhấp đúp câu trong danh sách để sửa');self.empty_hint.setWordWrap(True);self.empty_hint.setObjectName('muted');cl.addWidget(self.empty_hint)
        bar=QHBoxLayout();bar.addWidget(self.button('− 5s',lambda:self.seek(max(0,self.source_position()/1000-5*self.play_speed()))));self.play_button=self.button('▶ Phát',self.toggle_play);bar.addWidget(self.play_button);bar.addWidget(self.button('+ 5s',lambda:self.seek(self.source_position()/1000+5*self.play_speed())));self.time_label=QLabel('00:00:00,000');bar.addWidget(self.time_label,1);cl.addLayout(bar)
        self.scrub=QSlider(Qt.Horizontal);self.scrub.sliderMoved.connect(lambda x:self.seek(x/1000));cl.addWidget(self.scrub)
        self.editor_dialog=QDockWidget('Sửa câu đang chọn · kéo tiêu đề để di chuyển',self);self.editor_dialog.setObjectName('cue-editor');edit=QWidget();self.editor_dialog.setWidget(edit);self.addDockWidget(Qt.BottomDockWidgetArea,self.editor_dialog);self.editor_dialog.hide();el=QVBoxLayout(edit);tr=QHBoxLayout();self.start=QLineEdit();self.end=QLineEdit();self.start.setPlaceholderText('00:00:00,000');self.end.setPlaceholderText('00:00:00,000');tr.addWidget(QLabel('Từ'));tr.addWidget(self.start);tr.addWidget(QLabel('Đến'));tr.addWidget(self.end);el.addLayout(tr)
        self.text=QTextEdit();self.text.setAcceptRichText(False);self.text.setMinimumHeight(60);self.text.setMaximumHeight(150);self.text.setPlaceholderText('Chọn câu phụ đề ở danh sách hoặc timeline');el.addWidget(self.text)
        r=QHBoxLayout();self.cue_voice=QComboBox();self.cue_voice.addItem('Giọng mặc định','');[self.cue_voice.addItem(k,v) for k,v in VOICES.items()];r.addWidget(self.cue_voice);self.cue_rate=QSpinBox();self.cue_rate.setRange(-40,100);self.cue_rate.setSuffix(' %');self.cue_rate.setToolTip('Tốc độ bổ sung riêng câu này');r.addWidget(self.cue_rate);r.addWidget(self.button('Áp dụng câu',self.apply_cue,True));r.addWidget(self.button('Tạo / nghe riêng câu',self.sample));el.addLayout(r);el.addWidget(self.button('Đóng khung sửa',self.editor_dialog.hide));actions=QHBoxLayout();actions.addWidget(self.button('Sửa câu đang chọn…',self.show_editor));actions.addWidget(self.button('Bản nhẹ toàn phim…',self.make_proxy));cl.addLayout(actions);self.split.addWidget(center)
        right=QScrollArea();right.setWidgetResizable(True);right.setMinimumWidth(295);right.setMaximumWidth(375);props=QWidget();pr=QVBoxLayout(props);pr.setContentsMargins(12,0,5,0)
        pr.addWidget(QLabel('03  THIẾT LẬP'))
        pr.addWidget(self.button('Khung hình & màu sắc…',self.video_effects_dialog))
        self.effects_summary=QLabel();self.effects_summary.setWordWrap(True);pr.addWidget(self.effects_summary)
        stylebox=QGroupBox('Phụ đề');form=QFormLayout(stylebox)
        self.font_picker=QFontComboBox();self.font_picker.currentFontChanged.connect(self.visual_changed);form.addRow('Phông chữ',self.font_picker)
        self.font_size=self.spin(18,120,52,0,self.visual_changed);form.addRow('Cỡ chữ / 1080p',self.font_size)
        self.preset=QComboBox();self.preset.addItems(['Trắng · Viền đen','Vàng · Viền đen','Trắng · Nền đen']);self.preset.currentIndexChanged.connect(self.set_preset);form.addRow('Kiểu nổi bật',self.preset)
        self.color=self.button('Màu chữ',self.pick_text_color);form.addRow(self.color)
        self.bold=QCheckBox('In đậm');self.bold.toggled.connect(self.visual_changed);form.addRow(self.bold)
        self.box=QCheckBox('Nền đen sau chữ');self.box.toggled.connect(self.visual_changed);form.addRow(self.box)
        self.outline=self.spin(0,10,3,1,self.visual_changed);form.addRow('Viền đen',self.outline)
        self.shadow=self.spin(0,10,2,1,self.visual_changed);form.addRow('Bóng chữ',self.shadow)
        self.tx=self.spin(0,100,50,1,self.visual_changed);self.ty=self.spin(0,100,88,1,self.visual_changed);self.tw=self.spin(20,100,88,1,self.visual_changed)
        form.addRow('Vị trí X (%)',self.tx);form.addRow('Vị trí Y (%)',self.ty);form.addRow('Rộng chữ (%)',self.tw);pr.addWidget(stylebox)
        maskbox=QGroupBox('Che phụ đề tiếng Trung');mf=QFormLayout(maskbox)
        self.mask_on=QCheckBox('Bật vùng che');self.mask_on.toggled.connect(self.visual_changed);mf.addRow(self.mask_on);self.mask_mode=QComboBox();self.mask_mode.addItems(['Làm mờ vùng chọn','Phủ màu']);self.mask_mode.currentIndexChanged.connect(self.visual_changed);mf.addRow('Cách che',self.mask_mode);mf.addRow(self.mask_edit);self.mask_edit.toggled.connect(lambda:self.preview.overlay.update())
        self.mx=self.spin(0,99,8,1,self.visual_changed);self.my=self.spin(0,99,80,1,self.visual_changed);self.mw=self.spin(1,100,84,1,self.visual_changed);self.mh=self.spin(1,100,14,1,self.visual_changed)
        for label,w in [('X (%)',self.mx),('Y (%)',self.my),('Rộng (%)',self.mw),('Cao (%)',self.mh)]:mf.addRow(label,w)
        self.opacity=self.spin(.1,1,1,2,self.visual_changed);mf.addRow('Độ đậm phủ màu',self.opacity);mf.addRow(self.button('Màu vùng che',self.pick_mask_color));pr.addWidget(maskbox)
        speedbox=QGroupBox('Tốc độ & đồng bộ');sf=QFormLayout(speedbox)
        self.work=self.spin(.25,2,1,2,self.settings_changed);self.work.setSingleStep(.05);self.final=self.spin(.25,4,1,4,self.settings_changed);self.final.setSingleStep(.05)
        sf.addRow('Tốc độ dựng ×',self.work);sf.addRow('Tăng tốc bản cuối ×',self.final);sf.addRow(self.button('Bản cuối về tốc độ gốc',self.restore_speed));self.speed_label=QLabel();self.speed_label.setWordWrap(True);sf.addRow(self.speed_label);pr.addWidget(speedbox)
        voicebox=QGroupBox('Lồng tiếng Edge TTS');vf=QFormLayout(voicebox)
        self.voice=QComboBox();[self.voice.addItem(k,v) for k,v in VOICES.items()];self.voice.currentIndexChanged.connect(self.settings_changed);vf.addRow('Giọng mặc định',self.voice)
        self.rate=self.spin(-40,100,0,0,self.settings_changed);vf.addRow('Tốc độ đọc (%)',self.rate)
        self.workers=self.spin(1,6,3,0,self.settings_changed);vf.addRow('Số câu tạo cùng lúc',self.workers)
        self.maxfit=self.spin(1,3,1.6,2,self.settings_changed);vf.addRow('Giới hạn ép câu ×',self.maxfit)
        self.vol=self.spin(0,100,12,0,self.settings_changed);vf.addRow('Âm gốc (%)',self.vol)
        self.vvol=self.spin(0,100,100,0,self.settings_changed);vf.addRow('Voice Việt (%)',self.vvol)
        note=QLabel('Âm gốc giảm cả tiếng nói, nhạc và hiệu ứng. Giọng TTS cần mạng.');note.setWordWrap(True);note.setObjectName('muted');vf.addRow(note)
        self.generate_btn=self.button('Chọn lượt tạo voice…',self.show_batches,True);vf.addRow(self.generate_btn)
        vf.addRow(self.button('Tạo voice toàn dự án',self.generate))
        vf.addRow(self.button('Tạo voice các câu đang chọn',self.generate_selected))
        vf.addRow(self.button('Tạo voice vùng timeline',self.generate_region))
        vf.addRow(self.button('Rà thiếu / thử lại câu lỗi…',self.audit_voice_dialog))
        vf.addRow(self.button('Câu quá dài…',self.overflow_dialog))
        vf.addRow(self.button('Xóa voice các câu đang chọn',self.delete_selected_voice))
        vf.addRow(self.button('Xóa toàn bộ voice dự án',self.delete_all_voice))
        # Batch and audit actions live in the main toolbar.
        vf.addRow(self.button('Giảm nhạc toàn video…',self.music_dialog))
        vf.addRow(self.button('Phát video bằng CPU',self.switch_cpu))
        vf.addRow(self.button('Xuất vùng chọn / thử 10 giây',self.render_sample));vf.addRow(self.button('Lưu voice WAV',self.save_voice));vf.addRow(self.button('Khôi phục loa / tai nghe',self.restore_audio));pr.addWidget(voicebox);pr.addStretch();
        exportbox=QGroupBox('Xuất video');ef=QFormLayout(exportbox)
        self.export_mode=QComboBox();self.export_mode.addItem('Nhanh · tệp lớn hơn','veryfast');self.export_mode.addItem('Nhanh nhất · tệp lớn','ultrafast');self.export_mode.addItem('Nén gọn · chậm','medium')
        self.export_mode.currentIndexChanged.connect(self.export_mode_changed);ef.addRow('Chế độ',self.export_mode);pr.insertWidget(pr.count()-1,exportbox)
        for form in [form,mf,sf,vf,ef]:
            form.setRowWrapPolicy(QFormLayout.WrapLongRows);form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        for picker in [self.font_picker,self.preset,self.mask_mode,self.voice]:
            picker.setMinimumWidth(80);picker.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
        right.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);right.setWidget(props);self.split.addWidget(right);self.split.setSizes([315,670,300])
        tlbar=QHBoxLayout();tlbar.setContentsMargins(0,0,0,0);tlbar.addWidget(QLabel('TIMELINE · Ctrl+bấm chọn nhiều · Shift+kéo chọn vùng'));tlbar.addStretch();self.timeline_selection_label=QLabel('0 câu chọn');tlbar.addWidget(self.timeline_selection_label);self.timeline_snap=QCheckBox('Bắt dính');self.timeline_snap.setChecked(True);tlbar.addWidget(self.timeline_snap);tlbar.addWidget(self.button('Vừa vùng/lô',self.fit_timeline_scope));tlbar.addWidget(QLabel('Thu phóng'));self.zoom=QSlider(Qt.Horizontal);self.zoom.setRange(0,100);self.zoom.setValue(45);self.zoom.setFixedWidth(150);self.zoom.valueChanged.connect(self.zoom_changed);tlbar.addWidget(self.zoom);tlbar.addWidget(self.button('Vừa toàn bộ',self.fit_timeline));self.timeline_bar=QWidget();self.timeline_bar.setLayout(tlbar);outer.addWidget(self.timeline_bar)
        self.timeline=Timeline(self);self.timeline.seek.connect(self.seek);self.timeline.chosen.connect(self.select_id);self.timeline.setMaximumHeight(132);outer.addWidget(self.timeline)
        self.scroll=QScrollBar(Qt.Horizontal);self.scroll.valueChanged.connect(self.scroll_changed);outer.addWidget(self.scroll)
        self.region_bar=QWidget();rb=QHBoxLayout(self.region_bar);rb.setContentsMargins(0,0,0,0)
        self.select_region=QCheckBox('Chọn vùng');rb.addWidget(self.select_region)
        self.region_from=QDoubleSpinBox();self.region_to=QDoubleSpinBox()
        for widget in [self.region_from,self.region_to]:widget.setRange(0,999999);widget.setDecimals(3);widget.setSuffix(' s');widget.setFixedWidth(116);widget.editingFinished.connect(self.region_fields)
        rb.addWidget(QLabel('Từ'));rb.addWidget(self.region_from);rb.addWidget(QLabel('Đến'));rb.addWidget(self.region_to)
        rb.addWidget(self.button('Bỏ vùng',self.clear_region))
        self.follow_cursor=QCheckBox('Theo con trỏ');self.follow_cursor.setChecked(True);rb.addWidget(self.follow_cursor);rb.addStretch();outer.addWidget(self.region_bar)
        status=QHBoxLayout();self.status=QLabel('Sẵn sàng');self.status.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);status.addWidget(self.status,1);self.progress=QProgressBar();self.progress.setFixedWidth(200);self.progress.setRange(0,100);status.addWidget(self.progress);self.cancel_btn=self.button('Hủy tác vụ',self.cancel_job);self.cancel_btn.setEnabled(False);status.addWidget(self.cancel_btn);status.addWidget(self.button('Nhật ký',lambda:self.logs.setVisible(not self.logs.isVisible())));outer.addLayout(status)
        self.logs=QPlainTextEdit();self.logs.setReadOnly(True);self.logs.setMaximumBlockCount(500);self.logs.setMaximumHeight(120);self.logs.hide();outer.addWidget(self.logs)
    def spin(self,low,high,value,decimals,fn):
        w=QDoubleSpinBox();w.setRange(low,high);w.setDecimals(decimals);w.setValue(value);w.valueChanged.connect(fn);return w
    def log(self,text):
        self.logs.appendPlainText(time.strftime('%H:%M:%S')+'  '+text)
    def error(self,text):self.log(text);QMessageBox.warning(self,'HUYỄN ẢNH Studio',text)
    def guard(self):
        if self.busy:self.error('Tác vụ đang chạy. Hãy đợi hoàn tất hoặc bấm Hủy tác vụ.');return False
        return True
    def push_undo(self):
        if self.syncing or self.busy:return
        self.undo.append(self.p.to_dict());self.undo=self.undo[-40:];self.redo.clear()
    def undo_action(self):
        if not self.guard() or not self.undo:return
        self.redo.append(self.p.to_dict());data=self.undo.pop();self.apply_snapshot(data)
    def redo_action(self):
        if not self.guard() or not self.redo:return
        self.undo.append(self.p.to_dict());data=self.redo.pop();self.apply_snapshot(data)
    def apply_snapshot(self,data):
        oldmusic=copy.deepcopy(self.p.music_clean);oldvideo=self.p.video;self.editor_dirty=False;self.p=Project.from_dict(data);self.load_controls();self.preview.reset_size()
        if oldvideo!=self.p.video or oldmusic!=self.p.music_clean:self.load_preview_source()
        self.changed();self.select_id(self.selected)
    def changed(self,refresh=True,dirty=True):
        self.refresh_voice_state()
        if dirty:self.dirty=True
        if refresh:self.model.refresh()
        self.scrub.setMaximum(round(self.p.duration*1000));self.update_rates();self.update_scroll();self.timeline.update();self.on_position(self.source_position());self.refresh_voice_state()
        name=Path(self.p.video).name if self.p.video else 'Chưa chọn video'
        self.media_label.setText(name);self.media_label.setToolTip(self.p.video or name)
        self.media_details.setText(f'{self.p.width}×{self.p.height} · {stamp(self.p.duration)} · {len(self.p.cues):,} câu')
        self.setWindowTitle(('• ' if self.dirty else '')+'HUYỄN ẢNH Studio v0.2.11'+(' · '+self.project_path.name if self.project_path else ' · Dự án mới'))
    def load_controls(self):
        self.syncing=True;p=self.p;st=p.style;m=p.mask
        self.font_picker.setCurrentFont(QFont(st['font']));self.font_size.setValue(st['size']);self.bold.setChecked(st['bold']);self.box.setChecked(st['box']);self.outline.setValue(st['outline']);self.shadow.setValue(st['shadow'])
        self.tx.setValue(st['x']);self.ty.setValue(st['y']);self.tw.setValue(st['width']);self.mask_on.setChecked(m['enabled']);self.mask_mode.setCurrentIndex(0 if m['mode']=='blur' else 1)
        self.mx.setValue(m['x']);self.my.setValue(m['y']);self.mw.setValue(m['w']);self.mh.setValue(m['h']);self.opacity.setValue(m['opacity'])
        self.work.setValue(p.work_speed);self.final.setValue(p.final_speed);self.voice.setCurrentIndex(max(0,self.voice.findData(p.voice)));self.rate.setValue(p.tts_rate);self.workers.setValue(p.tts_workers);self.maxfit.setValue(p.max_fit);self.vol.setValue(p.original_volume*100);self.vvol.setValue(p.voice_volume*100)
        self.export_mode.setCurrentIndex(max(0,self.export_mode.findData(p.export_preset)))
        effects=effect_settings(p.video_effects)
        w,h=output_size(p)
        self.effects_summary.setText(f'Khung xuất: {w} × {h} · Zoom {effects["zoom"]*100:.0f}%' if effects['enabled'] else 'Khung xuất: giữ nguyên video gốc')
        self.syncing=False
    def video_effects_dialog(self):
        if not self.guard():return
        dialog=EffectsDialog(self,self.p.video_effects)
        if dialog.exec()!=QDialog.Accepted:return
        self.push_undo();self.p.video_effects=dialog.values;self.load_controls();self.changed(False)
        if dialog.preview_requested:self.render_effects_sample()
    def render_effects_sample(self):
        if not self.guard():return
        if self.editor_dirty and not self.commit_editor():return
        try:check_project(self.p)
        except Exception as e:self.error(str(e));return
        p=copy.deepcopy(self.p);cache=self.cache;path=cache/('Khung-hinh-'+uuid.uuid4().hex[:6]+'.mp4')
        start=max(0,self.source_position()/1000)/p.speed
        voice=voice_ready(p,cache)
        self.start_job(lambda c,r:export_video(p,cache,path,c,r,with_voice=voice,preview=start,allow_partial=True),self.export_done,'Xem thử khung hình 10 giây')
    def export_mode_changed(self):
        if self.syncing:return
        if self.busy:self.load_controls();return
        self.p.export_preset=self.export_mode.currentData();self.dirty=True
    def pull_visual_controls(self):
        self.syncing=True
        for widget,key in [(self.tx,'x'),(self.ty,'y')]:widget.setValue(self.p.style[key])
        for widget,key in [(self.mx,'x'),(self.my,'y'),(self.mw,'w'),(self.mh,'h')]:widget.setValue(self.p.mask[key])
        self.syncing=False
    def visual_changed(self,*args):
        if self.syncing:return
        if self.busy:self.load_controls();return
        self.push_undo();p=self.p
        p.style.update(font=self.font_picker.currentFont().family(),size=self.font_size.value(),bold=self.bold.isChecked(),box=self.box.isChecked(),outline=self.outline.value(),shadow=self.shadow.value(),x=self.tx.value(),y=self.ty.value(),width=self.tw.value())
        p.mask.update(enabled=self.mask_on.isChecked(),mode='blur' if self.mask_mode.currentIndex()==0 else 'solid',x=self.mx.value(),y=self.my.value(),w=min(self.mw.value(),100-self.mx.value()),h=min(self.mh.value(),100-self.my.value()),opacity=self.opacity.value())
        self.preview.overlay.update();self.dirty=True
    def pick_text_color(self):
        if not self.guard():return
        c=QColorDialog.getColor(QColor(self.p.style['color']),self)
        if c.isValid():self.push_undo();self.p.style['color']=c.name();self.changed(False)
    def pick_mask_color(self):
        if not self.guard():return
        c=QColorDialog.getColor(QColor(self.p.mask['color']),self)
        if c.isValid():self.push_undo();self.p.mask['color']=c.name();self.changed(False)
    def set_preset(self,*args):
        if self.syncing:return
        if not self.guard():return
        self.push_undo();i=self.preset.currentIndex();self.p.style.update(color='#FFE16A' if i==1 else '#FFFFFF',box=i==2,outline=3,bold=True,shadow=2);self.load_controls();self.changed(False)
    def settings_changed(self,*args):
        if self.syncing:return
        if self.busy:self.load_controls();return
        self.push_undo();self.p.work_speed=self.work.value();self.p.final_speed=self.final.value() if self.final.value()!=round(self.p.final_speed,4) else self.p.final_speed;self.p.voice=self.voice.currentData();self.p.tts_rate=round(self.rate.value());self.p.tts_workers=round(self.workers.value());self.p.max_fit=self.maxfit.value();self.p.original_volume=self.vol.value()/100;self.p.voice_volume=self.vvol.value()/100;self.changed()
    def restore_speed(self):
        if not self.guard():return
        self.push_undo();self.p.final_speed=1/self.p.work_speed
        self.syncing=True;self.final.setValue(self.p.final_speed);self.syncing=False;self.changed()
    def play_speed(self):return self.p.speed if self.preview_mode.currentIndex()==1 else self.p.work_speed
    def update_rates(self,*args):
        video_rate=self.play_speed();voice_rate=self.p.final_speed if self.preview_mode.currentIndex()==1 else 1
        rates=(video_rate,voice_rate)
        altered=getattr(self,'_nominal_rates',None)!=rates
        self._nominal_rates=rates
        if altered:self.player.setPlaybackRate(video_rate);self.voice_player.setPlaybackRate(voice_rate)
        self.audio.setVolume(self.p.original_volume);self.voice_audio.setVolume(min(1,self.p.voice_volume))
        self.speed_label.setText(f'Bản cuối: {self.p.speed:.3f}× tốc độ gốc\nThời lượng: {stamp(self.p.output_duration)}\nVoice bản cuối nhanh thêm {self.p.final_speed:.3f}× so với lúc dựng.')
        self.on_position(self.source_position())
        if altered:self.sync_voice(force=True)
    def on_frame(self,frame):
        if self.preview.show_frame(frame):
            self.frame_count+=1
            if self.frame_count==1:self.status.setText('Video đã hiển thị — sẵn sàng xem trước.')
    def show_editor(self):
        if not self.selected:
            if self.p.cues:self.select_id(self.p.cues[0].id)
            else:self.error('Hãy nhập SRT và chọn một câu để sửa.');return
        if not getattr(self,'_editor_placed',False):
            self.editor_dialog.setFloating(True);self.editor_dialog.resize(700,235)
            self.editor_dialog.move(self.x()+max(0,self.width()-730),self.y()+max(0,self.height()-270));self._editor_placed=True
        self.editor_dialog.show();self.editor_dialog.raise_();self.editor_dialog.activateWindow()
    def restore_audio(self):
        if not self.guard():return
        device=QMediaDevices.defaultAudioOutput()
        if device.isNull():self.error('Windows chưa có thiết bị phát âm thanh khả dụng. Chọn loa/tai nghe trong cài đặt âm thanh rồi thử lại.');return
        was_playing=self.player.playbackState()==QMediaPlayer.PlayingState
        self.player.pause();self.voice_player.pause();self.sample_player.stop()
        for player,attr,volume in [(self.player,'audio',self.p.original_volume),(self.voice_player,'voice_audio',min(1,self.p.voice_volume)),(self.sample_player,'sample_audio',1.)]:
            old=getattr(self,attr);new=QAudioOutput(device,self);new.setVolume(volume);player.setAudioOutput(new);setattr(self,attr,new);old.deleteLater()
        self.status.setText('Đã chọn lại âm thanh: '+device.description());self.log(self.status.text())
        if was_playing:self.player.play()
    def proxy_path(self):
        source=self.p.video
        key=hashlib.sha256((source+str(Path(source).stat().st_mtime_ns)).encode()).hexdigest()[:16]
        return self.cache/('preview-'+key+'.mp4')
    def available_full_proxy(self):
        try:
            path=self.proxy_path()
            return path if path.is_file() and path.stat().st_size>0 else None
        except OSError:return None
    def review_start(self):
        return self._batch_segment[0] if self._batch_segment is not None else self._preview_offset_ms/1000
    def source_position(self):
        return self.player.position()+getattr(self,'_preview_offset_ms',0)
    def load_preview_source(self):
        self._preview_offset_ms=0;self._preview_end=None;self._batch_segment=None;self._voice_offset_ms=0;self._load_batch_resume=None
        self.close_cpu();self._resume_cpu=None;self._needs_proxy=False;self.frame_count=0;self.player.stop();self.player.setSource(QUrl())
        self.cpu_mode=False
        if not self.p.video:return
        if self.p.music_clean.get('enabled'):
            try:full=self.music_preview_path()
            except Exception as e:self.status.setText(str(e));self.log(str(e));return
            self.cpu_mode=self.p.music_clean.get('preview_codec')=='av1'
            self.player.setVideoSink(None if self.cpu_mode else self.video_sink)
            self.player.setSource(QUrl.fromLocalFile(str(full)))
            if self.cpu_mode:self.cpu_seek(0)
            self.status.setText('Đang dùng âm gốc đã giảm nhạc · Voice Việt giữ riêng');return
        full=self.available_full_proxy()
        if full:
            self.player.setVideoSink(self.video_sink);self.player.setSource(QUrl.fromLocalFile(str(full)))
            self.status.setText('Đang dùng lại bản xem nhẹ toàn phim');return
        if not self.p.video_codec:self.p.video_codec=probe(self.p.video)['video_codec']
        # Qt's AV1 decoder may only support hardware. The external FFmpeg supplies CPU AV1.
        self.cpu_mode=self.p.video_codec=='av1'
        self.player.setVideoSink(None if self.cpu_mode else self.video_sink)
        self.player.setSource(QUrl.fromLocalFile(self.p.video))
        if self.cpu_mode:self.cpu_seek(0)
        self.status.setText('Phát trực tiếp video gốc'+(' · AV1 bằng CPU' if self.cpu_mode else ''))
    def music_preview_path(self):
        clean_audio_path(self.p)
        path=Path(self.p.music_clean.get('preview',''))
        if not path.is_file():raise ValueError('Thiếu bản xem giảm nhạc. Mở Giảm nhạc và bấm xử lý / tiếp tục để ghép lại.')
        return path
    def music_dialog(self,checked=False,sample=None):
        if not self.guard():return
        if not self.p.video or not self.p.has_audio:self.error('Hãy mở video có âm thanh trước.');return
        self.player.pause();self.voice_player.pause();self.sample_player.stop()
        dialog=QDialog(self);dialog.setWindowTitle('Giảm nhạc toàn video');dialog.resize(570,360)
        layout=QVBoxLayout(dialog)
        note=QLabel('AI ưu tiên giữ tiếng nói và giảm nhạc. Một số hiệu ứng có thể mất.\nGiữ một phần âm nền giúp còn hiệu ứng nhưng cũng còn nhạc.\nXử lý một lần; dùng lại khi phát và xuất, không phụ thuộc các lô voice Việt.')
        note.setWordWrap(True);layout.addWidget(note)
        state=QLabel('Hiện đang dùng: '+('âm đã giảm nhạc' if self.p.music_clean.get('enabled') else 'âm gốc'));layout.addWidget(state)
        form=QFormLayout();retain=QSpinBox();retain.setRange(0,50);retain.setSuffix(' %');retain.setValue(round((sample or self.p.music_clean).get('retain',.12)*100));form.addRow('Giữ lại âm nền',retain);threads=QSpinBox();threads.setRange(1,8);threads.setValue(self.p.music_threads);form.addRow('Luồng CPU giảm nhạc',threads);backend=QComboBox();backend.addItem('CPU · ONNX','cpu');backend.addItem('GPU NVIDIA · DirectML (thử nghiệm)','dml');backend.setCurrentIndex(1 if self.p.music_backend=='dml' else 0);form.addRow('Bộ xử lý',backend);layout.addLayout(form)
        tip=QLabel('0%: giảm nhạc mạnh hơn. 10–20%: giữ thêm nền và hiệu ứng.\nAI chỉ khởi động một lần cho mỗi lượt; giữ nguyên các đoạn đã xong.\nGPU: chạy CAI-GPU-GTX.cmd trước, rồi thử 30 giây.\nLuồng CPU: mặc định 2; thử 4 nếu máy còn dư CPU. Nhiều hơn chưa chắc nhanh hơn.\nThanh Âm gốc (%) điều chỉnh âm lượng kết quả khi xem / xuất.')
        tip.setWordWrap(True);layout.addWidget(tip)
        def begin(full):
            value=retain.value()/100;count=threads.value();device=backend.currentData();position=self.source_position();dialog.accept()
            if count!=self.p.music_threads:self.push_undo();self.p.music_threads=count;self.changed(False)
            if device!=self.p.music_backend:self.push_undo();self.p.music_backend=device;self.changed(False)
            if not self.save():return
            project=copy.deepcopy(self.p);cache=self.cache;base=self.available_full_proxy() or project.video
            start=min(max(0,position/1000),max(0,project.duration-30));segment=None if full else (start,min(project.duration,start+30))
            def work(cancel,report):
                result=build_music_reduction(project,cache,cancel,report,value,segment,fresh=not full)
                return make_music_preview(project,result,base,cancel,report) if full else result
            def done(result):
                if full:
                    self.push_undo();self.p.music_clean=result;self.load_preview_source();self._load_batch_resume=(position,False);self.changed();self.save()
                    self.status.setText('Đã áp dụng giảm nhạc toàn video. Bấm Phát để nghe cùng voice Việt.')
                else:QTimer.singleShot(0,lambda:self.music_dialog(sample=result))
            self.start_job(work,done,'Giảm nhạc toàn video' if full else 'Thử giảm nhạc 30 giây')
        layout.addWidget(self.button('Xử lý thử 30 giây tại con trỏ',lambda:begin(False)))
        if sample:
            layout.addWidget(QLabel(f"Lượt thử {sample.get('backend','cpu').upper()}: {sample.get('processing_seconds',0):.1f} giây xử lý (không gồm nạp mô hình)."))
            layout.addWidget(QLabel('Đoạn thử: '+stamp(sample['start'])+' – '+stamp(sample['end'])+' · Giữ nền '+str(round(sample['retain']*100))+'%'))
            row=QHBoxLayout()
            def listen(path):
                self.sample_player.stop();self.sample_player.setPlaybackRate(1);self.sample_audio.setVolume(1);self.sample_player.setSource(QUrl.fromLocalFile(path));self.sample_player.play()
            row.addWidget(self.button('Nghe âm gốc',lambda:listen(sample['original'])))
            row.addWidget(self.button('Nghe sau giảm nhạc',lambda:listen(sample['track'])))
            row.addWidget(self.button('Dừng nghe',self.sample_player.stop));layout.addLayout(row)
        layout.addWidget(self.button('Xử lý / tiếp tục toàn video',lambda:begin(True),True))
        def restore():
            position=self.source_position();self.push_undo();self.p.music_clean['enabled']=False;dialog.accept();self.load_preview_source();self._load_batch_resume=(position,False);self.changed();self.save()
        restore_btn=self.button('Dùng lại âm gốc',restore);restore_btn.setEnabled(bool(self.p.music_clean.get('enabled')));layout.addWidget(restore_btn)
        layout.addWidget(self.button('Đóng',dialog.reject));dialog.finished.connect(lambda _:self.sample_player.stop());dialog.exec()
    def close_cpu(self):
        if hasattr(self,'cpu_seek_timer'):self.cpu_seek_timer.stop()
        if self.cpu_decoder:self.cpu_decoder.close()
        self.cpu_decoder=None;self.cpu_pending=None
    def preview_tracks_changed(self):
        if self.cpu_mode and self.player.activeVideoTrack()!=-1:self.player.setActiveVideoTrack(-1)
    def preview_media_status(self,status):
        if status==QMediaPlayer.LoadedMedia:
            self.preview_tracks_changed()
            if self._load_batch_resume is not None:
                position,autoplay=self._load_batch_resume;self._load_batch_resume=None
                self.player.setPosition(max(0,position-self._preview_offset_ms));self.refresh_voice_state()
                if autoplay:self.player.play()
            resume=getattr(self,'_resume_cpu',None)
            if resume is not None:
                self._resume_cpu=None;position,playing=resume
                self.player.setPosition(position)
                if playing:self.player.play()
    def preview_error(self,error,msg):
        if msg:self.log('Video: '+msg)
        if self.p.video and not self.cpu_mode:QTimer.singleShot(0,self.switch_cpu)
    def switch_cpu(self,checked=False):
        if not self.p.video or self.cpu_mode:return
        try:audio_source=str(self.music_preview_path()) if self.p.music_clean.get('enabled') else self.p.video
        except Exception as e:self.status.setText(str(e));self.log(str(e));return
        position=self.source_position();playing=self.player.playbackState()==QMediaPlayer.PlayingState
        if self._preview_end is not None:
            self.close_cpu();self.player.pause();self.cpu_mode=True;self.player.setVideoSink(None)
            self.player.setActiveVideoTrack(-1);self.cpu_seek(position/1000)
            if playing:self.player.play()
            self.log('Phát video nhẹ của lô bằng CPU.');return
        self.close_cpu();self.player.pause();self.cpu_mode=True;self._preview_offset_ms=0;self._preview_end=None;self._batch_segment=None;self.refresh_voice_state()
        self.player.setVideoSink(None);self._resume_cpu=(position,playing)
        self.player.setSource(QUrl());self.player.setSource(QUrl.fromLocalFile(audio_source))
        self.cpu_seek(position/1000)
        self.log('Chuyển sang giải mã CPU trực tiếp. Không tạo bản video trung gian.')
    def cpu_seek(self,t):
        if not self.cpu_mode:return
        self.close_cpu();self._cpu_seek_target=max(0,min(t,max(0,self.p.duration-1/30)))
        self.cpu_seek_timer.start(90)
    def start_cpu_decoder(self):
        if self.cpu_mode and self.p.video:
            origin=self._preview_offset_ms/1000
            path=self.player.source().toLocalFile() if self._preview_end is not None else self.p.video
            codec='h264' if self._preview_end is not None else self.p.video_codec
            self.cpu_decoder=CPUFrames(path,codec,self.p.width,self.p.height,max(0,self._cpu_seek_target-origin),origin)
    def preview_clock(self):
        # Speech is the visual clock whenever available: never seek speech to chase frames.
        if (getattr(self,'voice_is_ready',False) and not self.busy
            and self.voice_player.playbackState()==QMediaPlayer.PlayingState
            and self.voice_player.mediaStatus()!=QMediaPlayer.EndOfMedia):
            return min(self.p.duration,(self.voice_player.position()*self.p.work_speed+getattr(self,'_voice_offset_ms',0))/1000)
        return min(self.p.duration,self.source_position()/1000)
    def present_cpu(self):
        import queue
        decoder=self.cpu_decoder
        if not self.cpu_mode or decoder is None:return
        if decoder.error:
            self.log('Giải mã CPU: '+decoder.error);self.status.setText('Không phát được bằng CPU — xem Nhật ký.')
            self.player.pause();self.close_cpu();return
        target=self.preview_clock();latest=None
        for _ in range(9):
            if self.cpu_pending is None:
                try:self.cpu_pending=decoder.frames.get_nowait()
                except queue.Empty:break
            timestamp,pixels=self.cpu_pending
            if timestamp>target+1/30:break
            latest=pixels;self.cpu_pending=None
        if latest is not None:
            frame=QImage(latest,decoder.width,decoder.height,decoder.width*3,QImage.Format_RGB888).copy()
            self.on_frame(frame)
        self.on_position(round(target*1000))
        if self.source_position()>=round(self.p.duration*1000) and self.player.playbackState()==QMediaPlayer.PlayingState:
            self.player.pause();self.voice_player.pause()
    def make_proxy(self):
        if not self.guard() or not self.p.video:return
        source=self.p.video;position=self.source_position();project=copy.deepcopy(self.p)
        target=self.proxy_path()
        def build(cancel,report):
            if target.exists():return str(target)
            tmp=target.with_suffix('.partial.mp4')
            try:
                report(0,'Tạo bản xem nhẹ 720p — chỉ cần làm một lần cho video này…')
                run([binary('ffmpeg'),'-y','-nostdin']+software_decode_args(self.p.video_codec)+['-i',source,'-map','0:v:0','-map','0:a:0?',
                     '-vf',"scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",
                     '-c:v','libx264','-preset','ultrafast','-crf','24','-pix_fmt','yuv420p',
                     '-c:a','aac','-b:a','128k','-movflags','+faststart','-progress','pipe:1','-nostats',tmp],
                    cancel,progress=lambda n:report(n,'Đang tạo bản xem nhẹ…'),total=self.p.duration)
                tmp.replace(target);return str(target)
            finally:tmp.unlink(missing_ok=True)
        def prepare(cancel,report):
            path=build(cancel,report)
            if project.music_clean.get('enabled'):
                clean_audio_path(project)
                return make_music_preview(project,project.music_clean,path,cancel,report)
            return path
        def done(path):
            if isinstance(path,dict):
                self.push_undo();self.p.music_clean=path;self.load_preview_source();self._load_batch_resume=(position,False);self.changed();self.save();return
            self.close_cpu();self.cpu_mode=False;self._preview_offset_ms=0;self._preview_end=None;self._batch_segment=None;self.refresh_voice_state();self.player.setVideoSink(self.video_sink)
            self._needs_proxy=False;self.player.setSource(QUrl.fromLocalFile(path));self.frame_count=0
            QTimer.singleShot(600,lambda:self.player.setPosition(position))
            self.status.setText('Đã mở bản xem nhẹ. Bấm Phát; khi xuất vẫn dùng video gốc.')
        self.start_job(prepare,done,'Chuẩn bị bản xem nhẹ')
    def on_position(self,ms):
        self._screen_time=ms/1000
        t=ms/1000;self.time_label.setText(f'Gốc {stamp(t)} · Xem {stamp(t/self.play_speed())}')
        if not self.scrub.isSliderDown():self.scrub.setValue(ms)
        active=[c.text for c in self.p.cues if c.start<=t<c.end and plain(c.text)]
        self.preview.overlay.text='\n'.join(active);self.preview.overlay.update();self.timeline.cursor=t
        if self.player.playbackState()==QMediaPlayer.PlayingState:
            self.reveal_cursor(t)
            if ((self.range_play_end is not None and t>=self.range_play_end)
                or (self._preview_end is not None and t>=self._preview_end)):
                self.player.pause();self.voice_player.pause();self.range_play_end=None
        self.timeline.update()
    def reveal_cursor(self,t):
        if not self.follow_cursor.isChecked():return
        width=max(1,(self.timeline.width()-108)/self.timeline.zoom)
        if t<self.timeline.offset or t>self.timeline.offset+width*.95:self.scroll.setValue(round(max(0,t-width*.2)*100))
    def set_region(self,a,b):
        a=round(max(0,min(self.p.duration,a)),3);b=round(max(a,min(self.p.duration,b)),3)
        self.selection=(a,b);self.region_from.setValue(a);self.region_to.setValue(b);self.timeline.update()
    def region_fields(self):
        a=self.region_from.value();b=self.region_to.value()
        if b<=a:self.error('Mốc cuối vùng phải lớn hơn mốc đầu.');return
        self.set_region(a,b)
    def clear_region(self):
        self.selection=None;self.range_play_end=None;self.select_region.setChecked(False);self.timeline.update()
    def region_ids(self):
        if not self.selection or self.selection[1]<=self.selection[0]:raise ValueError('Giữ Shift và kéo trên timeline để chọn vùng, hoặc nhập Từ / Đến.')
        a,b=self.selection
        return [c.id for c in self.p.cues if plain(c.text) and c.start<b and c.end>a]
    def generate_region(self):
        try:ids=self.region_ids()
        except Exception as e:self.error(str(e));return
        self.generate(only_ids=ids)
    def play_region(self):
        try:self.region_ids()
        except Exception as e:self.error(str(e));return
        if self._preview_end is not None and not (self.review_start()<=self.selection[0]<self.selection[1]<=self._preview_end):
            self.status.setText('Vùng chọn nằm ngoài lô đang mở. Chọn lô khác trước khi nghe.');return
        def play():
            self.range_play_end=self.selection[1];self.seek(self.selection[0]);self.reveal_cursor(self.selection[0]);self.player.play()
        self.ensure_review(play)

    def seek(self,t):
        t=min(self.p.duration,max(0,t));self.cpu_seek(t);self.player.setPosition(max(0,round(t*1000)-self._preview_offset_ms));self.on_position(round(t*1000));self.sync_voice(force=True)
    def toggle_play(self):
        if self.busy or not self.p.video:return
        self.sample_player.stop();self.range_play_end=None
        if self.player.playbackState()==QMediaPlayer.PlayingState:self.player.pause()
        else:
            limit=self._preview_end if self._preview_end is not None else self.p.duration
            if self.source_position()>=round(limit*1000)-100:self.seek(self.review_start())
            if self.cpu_mode and self.cpu_decoder is None:self.cpu_seek(self.source_position()/1000)
            self.ensure_review(self.player.play)
    def ensure_review(self,callback):
        if not self.guard():return
        if self.editor_dirty and not self.commit_editor():return
        if voice_ready(self.p,self.cache):self.refresh_voice_state();callback();return
        if cached_voice_exists(self.p,self.cache):self.rebuild_existing(after=callback)
        else:callback()
    def rebuild_existing(self,checked=False,after=None):
        if not self.guard():return
        if self.editor_dirty and not self.commit_editor():return
        if not self.p.duration:self.error('Hãy chọn video trước.');return
        p=copy.deepcopy(self.p)
        def done(result):
            self.voices_done(result)
            if after:after()
        self.start_job(lambda c,r:rebuild_voice_track(p,self.cache,c,r),done,'Ghép voice đã có — không gọi lại Edge TTS')

    def play_state(self,state):
        self.play_button.setText('Ⅱ Dừng' if state==QMediaPlayer.PlayingState else '▶ Phát')
        if state!=QMediaPlayer.PlayingState:self.voice_player.pause()
        else:
            self.sync_voice(force=True)
            if not self.cpu_mode and not self.frame_count:QTimer.singleShot(3000,self.check_video_frames)
    def check_video_frames(self):
        if not self.cpu_mode and not self.frame_count and self.player.playbackState()==QMediaPlayer.PlayingState:self.switch_cpu()
    def sync_voice(self,force=False):
        if not getattr(self,'voice_is_ready',False) or self.busy:self.voice_player.pause();return
        base=self.play_speed();voice_rate=self.p.final_speed if self.preview_mode.currentIndex()==1 else 1
        target=round(((self.source_position() if hasattr(self,'source_position') else self.player.position())-getattr(self,'_voice_offset_ms',0))/self.p.work_speed)
        now=time.monotonic()
        if self.voice_player.mediaStatus()==QMediaPlayer.LoadingMedia:return
        if force:
            # Only user seek/play/speed changes reposition speech, never the polling timer.
            self.player.setPlaybackRate(base);self.voice_player.setPlaybackRate(voice_rate)
            self.voice_player.setPosition(target);self._sync_last_adjust=now
        if self.player.playbackState()!=QMediaPlayer.PlayingState:return
        if self.voice_player.mediaStatus()==QMediaPlayer.EndOfMedia:return
        if self.voice_player.playbackState()!=QMediaPlayer.PlayingState:
            self.voice_player.play();return
        if force or now-getattr(self,'_sync_last_adjust',0)<1.5:return
        # Qt players have separate clocks. Keep the voice continuous, following it with video.
        if self.voice_player.mediaStatus() in (QMediaPlayer.LoadingMedia,QMediaPlayer.StalledMedia):return
        error_ms=self.voice_player.position()-target
        rate=preview_follow_rate(base,error_ms)
        if abs(self.player.playbackRate()-rate)>base*.003:self.player.setPlaybackRate(rate)
        self._sync_last_adjust=now
    def refresh_voice_state(self):
        batch=None;ready=voice_ready(self.p,self.cache);self._voice_offset_ms=0
        was_ready=getattr(self,'voice_is_ready',False);self.voice_is_ready=ready
        if was_ready and not ready:self.player.setPlaybackRate(self.play_speed())
        src=QUrl.fromLocalFile(str(voice_track_path(self.cache))) if ready else QUrl()
        if self.voice_player.source()!=src:self.voice_player.setSource(src)
        if hasattr(self,'voice_summary'):
            spoken=[c for c in self.p.cues if plain(c.text)];bad=sum(self.row_status(c)[0]=='long' for c in spoken)
            count=sum(self.row_status(c)[0] in ('ready','cached','long') for c in spoken)
            self.voice_summary.setText(f'Voice: {count}/{len(spoken)} · {bad} câu dài')
            self.voice_summary.setToolTip(f'Voice: {count}/{len(spoken)} câu có MP3 · {bad} câu dài'+(' · Đang nghe voice riêng của lô' if ready and batch is not None else ' · Đã ghép để nghe' if ready else ' · Cần ghép để nghe'))

    def row_status(self,c):
        if not plain(c.text):return 'empty','Trống'
        raw=self.cache/(raw_key(c,self.p)+'.mp3')
        if not raw.is_file() or raw.stat().st_size==0:return 'none','Chưa tạo'
        row=self.rows.get(c.id)
        if not row:return ('cached','Có MP3') if (self.cache/(raw_key(c,self.p)+'.mp3')).exists() else ('none','Chưa tạo')
        raw=self.cache/(raw_key(c,self.p)+'.mp3')
        if str(raw)!=row.get('raw'):return 'none','Cần tạo lại'
        factor=max(1,row['duration']/((c.end-c.start)/self.p.work_speed))
        if factor>self.p.max_fit+.0001:return 'long',f'Dài {factor:.2f}×'
        if not voice_ready_cached(self):return 'cached',f'Có MP3'
        return 'ready',f'{factor:.2f}×'
    def filter_rows(self,*args):self.model.query=self.search.text();self.model.only_long=self.long_only.isChecked();self.model.refresh()
    def table_clicked(self,index):
        c=self.p.cues[self.model.indices[index.row()]];self.navigate_cue(c.id)
    def navigate_cue(self,id,preserve_selection=False):
        if not self.guard():return
        if self.editor_dirty and not self.commit_editor():return
        cue=next((c for c in self.p.cues if c.id==id),None)
        if cue is None:return
        if not preserve_selection:self.timeline.choose({id},id)
        self.player.pause();t=cue.start
        self.seek(t);self.reveal_cursor(t)
    def editor_changed(self,*args):
        if not self.editor_loading and self.selected:self.editor_dirty=True;self.dirty=True
    def select_id(self,id):
        if self.editor_dirty and id!=self.selected and not self.commit_editor():return
        self.editor_loading=True
        self.selected=id;c=next((c for c in self.p.cues if c.id==id),None)
        valid={cue.id for cue in self.p.cues};self.timeline.selected_ids.intersection_update(valid)
        if id not in self.timeline.selected_ids:self.timeline.selected_ids={id} if c else set()
        self.timeline_selection_label.setText(f'{len(self.timeline.selected_ids)} câu chọn')
        if not c:self.start.clear();self.end.clear();self.text.clear();self.editor_dirty=False;self.editor_loading=False;return
        self.start.setText(stamp(c.start));self.end.setText(stamp(c.end));self.text.setPlainText(c.text);self.cue_voice.setCurrentIndex(max(0,self.cue_voice.findData(c.voice)));self.cue_rate.setValue(c.tts_rate)
        self.editor_dirty=False;self.editor_loading=False
        for r,i in enumerate(self.model.indices):
            if self.p.cues[i].id==id:self.table.selectRow(r);self.table.scrollTo(self.model.index(r,0));break
        self.timeline.update()
    def apply_cue(self):
        if self.commit_editor():self.select_id(self.selected);return True
        return False
    def commit_editor(self):
        if not self.guard():return False
        c=next((c for c in self.p.cues if c.id==self.selected),None)
        if not c:return False
        try:
            a=parse_time(self.start.text());b=parse_time(self.end.text());validate_cue(Cue(a,b,''))
            if self.p.duration and b>self.p.duration+.1:raise ValueError('Mốc kết thúc vượt thời lượng video.')
        except ValueError as e:self.error(str(e));return False
        self.push_undo();c.start=a;c.end=b;c.text=self.text.toPlainText();c.voice=self.cue_voice.currentData();c.tts_rate=self.cue_rate.value();self.p.cues.sort(key=lambda c:c.start);self.editor_dirty=False;self.changed();return True
    def add_cue(self):
        if not self.guard():return
        t=self.source_position()/1000
        if self.p.duration and t>=self.p.duration-.04:t=max(0,self.p.duration-2)
        c=Cue(t,min(t+2,self.p.duration) if self.p.duration else t+2,'Phụ đề mới')
        self.push_undo();self.p.cues.append(c);self.p.cues.sort(key=lambda c:c.start);self.changed();self.select_id(c.id)
    def delete_cue(self):
        if not self.guard() or not self.selected:return
        self.push_undo();self.editor_dirty=False;self.p.cues=[c for c in self.p.cues if c.id!=self.selected];self.changed();self.select_id(None)
    def zoom_changed(self,value):
        self.timeline.zoom=10**(-.1+value*.035);self.update_scroll();self.timeline.update()
    def update_scroll(self):
        duration=self.p.duration;visible=max(1,(self.timeline.width()-108)/self.timeline.zoom)
        self.scroll.setRange(0,round(max(0,duration-visible)*100));self.scroll.setPageStep(round(visible*100))
    def scroll_changed(self,value):self.timeline.offset=value/100;self.timeline.update()
    def fit_timeline_scope(self):
        scope=self.selection or self._batch_segment
        if not scope and self.timeline.selected_ids:
            cues=[c for c in self.p.cues if c.id in self.timeline.selected_ids]
            if cues:scope=(min(c.start for c in cues),max(c.end for c in cues))
        if not scope or scope[1]<=scope[0]:self.fit_timeline();return
        a,b=scope;padding=max(.1,(b-a)*.04);a=max(0,a-padding);b=min(self.p.duration,b+padding)
        self.timeline.zoom=max(.005,(self.timeline.width()-120)/max(.04,b-a))
        self.update_scroll();self.scroll.setValue(round(a*100));self.timeline.update()
    def fit_timeline(self):
        self.timeline.zoom=max(.005,(self.timeline.width()-120)/max(1,self.p.duration));self.scroll.setValue(0);self.update_scroll();self.timeline.update()
    def toggle_screen_selection(self,on):
        if not on:return
        if self.busy or self.preview.overlay.frame.isNull():
            self.region_select.setChecked(False);self.status.setText('Phát video tới frame cần sửa rồi dừng trước khi chọn vùng.');return
        self.player.pause();self.voice_player.pause();self.status.setText('Kéo một hình chữ nhật quanh chữ Trung hoặc watermark trên video.')

    def new_screen_region(self,rect):
        p=self.p;t=min(max(0,self.source_position()/1000),max(0,p.duration-.1))
        region=dict(id=uuid.uuid4().hex[:12],start=t,end=min(p.duration,t+5),x=rect.x()/p.width*100,y=rect.y()/p.height*100,w=rect.width()/p.width*100,h=rect.height()/p.height*100,text='',source_text='',mode='blur',size=48,color='#FFFFFF',strength=18,enabled=True)
        self.edit_screen_region(region)

    def edit_screen_region(self,region):
        if not self.guard():return
        self.player.pause();self.voice_player.pause();r=copy.deepcopy(region)
        dialog=QDialog(self);dialog.setWindowTitle('Chữ Việt / làm mờ vùng đã chọn');dialog.resize(780,620);layout=QVBoxLayout(dialog)
        note=QLabel('Vùng cố định theo vị trí trên hình. OCR chỉ đọc chữ trong frame hiện tại; bạn nhập bản tiếng Việt bên dưới.\nTên truyện có thể dùng nhiều dòng. Mốc thời gian tính theo video gốc.');note.setWordWrap(True);layout.addWidget(note)
        body=QHBoxLayout();form=QFormLayout();start=QLineEdit(stamp(r['start']));end=QLineEdit(stamp(r['end']));form.addRow('Từ',start);form.addRow('Đến',end)
        form.addRow(self.button('Áp dụng suốt video',lambda:(start.setText(stamp(0)),end.setText(stamp(self.p.duration)))))
        geometry={}
        for key,label in [('x','X (%)'),('y','Y (%)'),('w','Rộng (%)'),('h','Cao (%)')]:
            spin=QDoubleSpinBox();spin.setRange(0 if key in ('x','y') else .1,100);spin.setDecimals(2);spin.setValue(r[key]);geometry[key]=spin;form.addRow(label,spin)
        mode=QComboBox();mode.addItem('Làm mờ','blur');mode.addItem('Phủ nền tối','solid');mode.addItem('Chỉ thêm chữ','none');mode.setCurrentIndex(mode.findData(r['mode']));form.addRow('Che chữ / watermark',mode)
        strength=QSpinBox();strength.setRange(1,40);strength.setValue(r['strength']);form.addRow('Độ mờ',strength)
        size=QSpinBox();size.setRange(8,200);size.setValue(r['size']);form.addRow('Cỡ chữ (theo 1080p)',size)
        color=[r['color']]
        def pick_color():
            value=QColorDialog.getColor(QColor(color[0]),dialog)
            if value.isValid():color[0]=value.name()
        form.addRow(self.button('Màu chữ Việt',pick_color));enabled=QCheckBox('Hiển thị vùng này');enabled.setChecked(r.get('enabled',True));form.addRow(enabled);body.addLayout(form)
        right=QVBoxLayout();right.addWidget(QLabel('Chữ nhận diện từ hình (có thể sửa/copy)'));source=QPlainTextEdit(r.get('source_text',''));source.setMaximumHeight(110);right.addWidget(source)
        right.addWidget(QLabel('Chữ tiếng Việt / tên truyện'));text=QPlainTextEdit(r['text']);text.setPlaceholderText('Nhập tên truyện tiếng Việt. Để trống nếu chỉ cần làm mờ.');right.addWidget(text,1)
        def collect():
            draft=dict(r,start=parse_time(start.text()),end=parse_time(end.text()),text=text.toPlainText(),source_text=source.toPlainText(),mode=mode.currentData(),size=size.value(),color=color[0],strength=strength.value(),enabled=enabled.isChecked())
            draft.update({key:value.value() for key,value in geometry.items()});validate_screen_region(draft,self.p.duration);return draft
        def apply():
            try:draft=collect()
            except Exception as e:self.error(str(e));return
            self.push_undo();self.p.screen_regions=[draft if x['id']==draft['id'] else x for x in self.p.screen_regions]
            if not any(x['id']==draft['id'] for x in self.p.screen_regions):self.p.screen_regions.append(draft)
            self.changed();dialog.accept()
        def ocr():
            try:
                draft=collect();image=self.preview.overlay.frame
                if image.isNull():raise ValueError('Chưa có frame video để quét.')
                x,y,w,h=region_pixels(self.p,draft);crop=image.copy(QRectF(x*image.width()/self.p.width,y*image.height()/self.p.height,w*image.width()/self.p.width,h*image.height()/self.p.height).toRect())
                path=self.cache/('ocr-'+uuid.uuid4().hex+'.png')
                if not crop.save(str(path)):raise ValueError('Không lưu được ảnh vùng OCR.')
            except Exception as e:self.error(str(e));return
            dialog.accept()
            def work(cancel,report):
                try:report(10,'Đang nhận diện chữ trong vùng frame…');return dict(text=recognize_screen_text(path))
                except Exception as e:return dict(error=str(e))
                finally:path.unlink(missing_ok=True)
            def done(value):
                if 'error' in value:self.error(value['error'])
                else:draft['source_text']=value['text']
                self.status.setText('Kiểm tra kết quả OCR rồi nhập chữ Việt; các thiết lập vùng được giữ.')
                QTimer.singleShot(0,lambda:self.edit_screen_region(draft))
            self.start_job(work,done,'OCR frame hiện tại')
        right.addWidget(self.button('Quét chữ Trung trong vùng (OCR)',ocr));hint=QLabel('OCR cần cài một lần bằng CAI-OCR.cmd. Không tự dịch; chữ Việt do bạn nhập.');hint.setWordWrap(True);right.addWidget(hint);body.addLayout(right,1);layout.addLayout(body,1)
        actions=QHBoxLayout();actions.addWidget(self.button('Áp dụng vùng',apply,True));actions.addWidget(self.button('Hủy',dialog.reject));layout.addLayout(actions);dialog.exec();dialog.deleteLater()

    def manage_screen_regions(self):
        if not self.guard():return
        dialog=QDialog(self);dialog.setWindowTitle('Các vùng chữ / làm mờ');dialog.resize(840,440);layout=QVBoxLayout(dialog)
        table=QTableWidget(0,4);table.setHorizontalHeaderLabels(['Từ','Đến','Chữ Việt / vùng','Hiển thị']);table.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection);table.setEditTriggers(QAbstractItemView.NoEditTriggers);layout.addWidget(table)
        ids=[]
        def refill():
            ids[:]=[r['id'] for r in self.p.screen_regions];table.setRowCount(len(ids))
            for i,r in enumerate(self.p.screen_regions):
                for j,value in enumerate([stamp(r['start']),stamp(r['end']),r['text'] or 'Vùng che '+r['mode'],'Bật' if r.get('enabled',True) else 'Tắt']):table.setItem(i,j,QTableWidgetItem(value))
        def selected():
            i=table.currentRow();return next((r for r in self.p.screen_regions if 0<=i<len(ids) and r['id']==ids[i]),None)
        def edit():
            r=selected()
            if r:self.seek(r['start']);dialog.accept();QTimer.singleShot(0,lambda:self.edit_screen_region(r))
        def delete():
            r=selected()
            if r and QMessageBox.question(dialog,'Xóa vùng','Xóa vùng chữ / làm mờ này? Ctrl+Z để hoàn tác.')==QMessageBox.Yes:
                self.push_undo();self.p.screen_regions=[x for x in self.p.screen_regions if x['id']!=r['id']];self.changed();refill()
        row=QHBoxLayout();row.addWidget(self.button('Tới mốc và sửa vùng',edit));row.addWidget(self.button('Xóa vùng',delete));row.addWidget(self.button('Đóng',dialog.accept));layout.addLayout(row);refill();dialog.exec();dialog.deleteLater()

    def focus_preview(self):
        focused=self.split.widget(0).isVisible()
        self.region_bar.setVisible(not focused);self.split.widget(0).setVisible(not focused);self.split.widget(2).setVisible(not focused)
        self.timeline.setVisible(not focused);self.timeline_bar.setVisible(not focused);self.scroll.setVisible(not focused)
        self.focus_button.setText('Về bố cục dựng' if focused else 'Phóng video')
    def fullscreen(self):self.showNormal() if self.isFullScreen() else self.showFullScreen()
    def import_video(self):
        if not self.guard():return
        path,_=QFileDialog.getOpenFileName(self,'Chọn video','','Video (*.mp4 *.mkv *.mov *.avi *.webm *.m4v);;Tất cả (*)')
        if not path:return
        self.start_job(lambda cancel,report:probe(path),lambda info:self.video_loaded(path,info),'Đọc thông tin video')
    def video_loaded(self,path,info):
        if not info['width']:self.error('Tệp này không có hình ảnh video.');return
        self.push_undo();self.player.stop()
        if path!=self.p.video:self.p.voice_batch_kept=[];self.p.batch_reviewed={};self.p.music_clean={}
        self.p.video=path
        for k,v in info.items():setattr(self.p,k,v)
        self.preview.reset_size();self.load_preview_source();self.changed();self.fit_timeline();self.log('Đã mở video: '+Path(path).name)
        if any(c.end>self.p.duration+.1 for c in self.p.cues):self.error('Một số mốc SRT dài hơn video vừa chọn. Hãy kiểm tra nguồn trước khi tạo voice / xuất.')
    def remove_srt(self):
        if not self.guard():return
        if not self.p.cues:self.status.setText('Dự án chưa có phụ đề để xóa.');return
        if QMessageBox.question(self,'Xóa toàn bộ SRT',f'Xóa toàn bộ {len(self.p.cues)} câu phụ đề khỏi dự án và timeline?\nBao gồm tất cả các phần SRT đã nhập, kể cả câu đang bị ẩn bởi bộ lọc.\nGiữ video, file SRT gốc và voice đã tạo trong bộ nhớ đệm.\nCtrl+Z để hoàn tác.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        self.push_undo();self.player.pause();self.voice_player.stop();self.sample_player.stop();self.editor_dirty=False
        self.timeline.choose([]);self.p.cues=[];self.p.voice_batch_kept=[];self.p.batch_reviewed={};self.rows={};self.select_id(None);self.clear_region();self.editor_dialog.hide();self.changed()
        self.status.setText('Đã xóa toàn bộ SRT khỏi dự án. Bấm + SRT để nhập file khác; Ctrl+Z để khôi phục.')
    def delete_selected_voice(self):self.delete_voice(False)
    def delete_all_voice(self):self.delete_voice(True)
    def delete_voice(self,all_voice=False):
        if not self.guard():return
        if self.editor_dirty and not self.commit_editor():return
        ids=None if all_voice else list(self.timeline.selected_ids)
        if not all_voice and not ids:self.status.setText('Chọn câu trên timeline trước khi xóa voice.');return
        keys={raw_key(c,self.p) for c in self.p.cues if all_voice or c.id in ids}
        affected=sum(raw_key(c,self.p) in keys for c in self.p.cues)
        message='Xóa toàn bộ voice đang lưu của dự án, kể cả voice từ SRT cũ?' if all_voice else f'Xóa voice của {len(ids)} câu đã chọn? Có {affected} câu dùng chung các tệp này và sẽ cần tạo lại voice.'
        message+='\nGiữ video, bản nhẹ và nội dung phụ đề. Voice được chuyển vào thư mục voice-trash trong bộ nhớ dự án để có thể phục hồi thủ công; Ctrl+Z không khôi phục file voice.'
        if QMessageBox.question(self,'Xóa voice đã tạo',message)!=QMessageBox.Yes:return
        self.player.pause();self.voice_player.stop();self.voice_player.setSource(QUrl());self.sample_player.stop();self.sample_player.setSource(QUrl())
        try:result=remove_cached_voice(self.p,self.cache,ids)
        except Exception as e:self.error(str(e));self.refresh_voice_state();return
        if all_voice:self.rows={}
        else:
            for id in result['affected']:self.rows.pop(id,None)
        self.changed();self.status.setText('Đã xóa voice khỏi phần đang dùng. Phụ đề và video được giữ.')
        if result['backup']:self.log('Bản lưu voice đã xóa: '+result['backup'])

    def import_srt(self):
        if not self.guard():return
        if self.editor_dirty and not self.commit_editor():return
        paths,_=QFileDialog.getOpenFileNames(self,'Nhập một hoặc nhiều phần SRT','','SubRip (*.srt)')
        if not paths:return
        try:
            files=[(Path(path).name,read_srt(path)) for path in paths]
            report=inspect_srt_import(self.p.cues,files)
        except Exception as e:self.error(str(e));return
        overlaps=[r for r in report['rows'] if r['kind']=='overlap']
        duplicates=sum(r['kind']=='duplicate' for r in report['rows']);repeated=sum(r['kind']=='repeated' for r in report['rows'])
        choices={}
        if overlaps or repeated:
            dialog=QDialog(self);dialog.setWindowTitle('Kiểm tra SRT trước khi nhập');dialog.resize(1000,600);layout=QVBoxLayout(dialog)
            summary='\n'.join(f"{r['file']}: {r['total']} câu · đã có {r['duplicate']} · chồng mốc {r['overlap']} · lặp lời khác mốc {r['repeated']}" for r in report['files'])
            label=QLabel(summary+'\nCâu trùng cả lời và mốc tự bỏ qua. Câu mới tự thêm. Lời giống nhưng khác mốc có thể là thoại lặp, mặc định giữ.\nThay câu chồng mốc sẽ xóa các câu đang có được liệt kê ở cột đối chiếu; có thể Ctrl+Z hoàn tác.');label.setWordWrap(True);layout.addWidget(label)
            review=[r for r in report['rows'] if r['kind'] in ('overlap','repeated')]
            table=QTableWidget(len(review),5);table.setHorizontalHeaderLabels(['File / mốc','Nội dung mới','Đối chiếu đang có','Phát hiện','Xử lý']);table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch);table.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch);table.setColumnWidth(0,205);table.setColumnWidth(4,180);layout.addWidget(table,1);controls=[]
            for i,row in enumerate(review):
                cue=row['cue'];values=[row['file']+'\n'+stamp(cue.start)+' → '+stamp(cue.end),cue.text,row['old_text'],'Chồng / trùng mốc' if row['kind']=='overlap' else 'Lặp lời, khác mốc']
                for j,value in enumerate(values):item=QTableWidgetItem(value);item.setToolTip(value);table.setItem(i,j,item)
                select=QComboBox();select.addItem('Bỏ qua câu mới','skip');select.addItem('Giữ thêm câu mới','keep')
                if row['kind']=='overlap':select.addItem('Thay câu chồng mốc','replace')
                else:select.setCurrentIndex(1)
                table.setCellWidget(i,4,select);controls.append((cue.id,select))
            table.resizeRowsToContents()
            actions=QHBoxLayout();actions.addWidget(self.button('Áp dụng kết quả kiểm tra',dialog.accept,True));actions.addWidget(self.button('Hủy nhập',dialog.reject));layout.addLayout(actions)
            accepted=dialog.exec()==QDialog.Accepted
            if accepted:choices={id:control.currentData() for id,control in controls}
            dialog.deleteLater()
            if not accepted:return
        cues=apply_srt_import(self.p.cues,report,choices)
        old_ids={c.id for c in self.p.cues};new_ids={c.id for c in cues};added=len(new_ids-old_ids);removed=old_ids-new_ids
        for row in report['files']:self.log(f"SRT {row['file']}: {row['duplicate']}/{row['total']} câu đã có, {row['overlap']} câu chồng mốc.")
        if not added and not removed:
            self.status.setText(f'SRT đã có hoặc không có câu mới được chọn · bỏ qua {duplicates} câu trùng.');return
        self.player.pause();self.voice_player.stop();self.sample_player.stop();self.push_undo();self.editor_dirty=False
        self.p.cues=cues;self.p.voice_batch_kept=[];self.p.batch_reviewed={}
        for id in removed:self.rows.pop(id,None)
        self.timeline.choose([id for id in self.timeline.selected_ids if id not in removed])
        self.changed();self.select_id(next((c.id for c in cues if c.id not in old_ids),cues[0].id if cues else None))
        self.status.setText(f'Đã thêm {added} câu · thay {len(removed)} câu cũ · bỏ qua {duplicates} câu trùng hoàn toàn.');self.log(self.status.text())
        if self.p.duration and cues and max(c.end for c in cues)>self.p.duration+.1:self.error('SRT dài hơn video. Giữ nguyên mốc; hãy chọn đúng video nguồn trước khi xuất.')
    def confirm_discard(self):
        if not self.dirty:return True
        result=QMessageBox.question(self,'Lưu dự án','Lưu thay đổi dự án trước khi tiếp tục?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel)
        if result==QMessageBox.Cancel:return False
        if result==QMessageBox.Save:return self.save()
        return True
    def new_project(self):
        if not self.guard() or not self.confirm_discard():return
        self.close_cpu();self.cpu_mode=False;self._preview_offset_ms=0;self._preview_end=None;self._batch_segment=None;self._load_batch_resume=None;self.player.stop();self.voice_player.stop();self._needs_proxy=False;self.editor_dirty=False;self.p=Project();self.project_path=None;self.cache_id=uuid.uuid4().hex;self.cache=self.cache_root/self.cache_id;self.cache.mkdir(parents=True,exist_ok=True);self.rows={};self.undo=[];self.redo=[];self.player.setSource(QUrl());self.load_controls();self.preview.reset_size();self.clear_region();self.selected=None;self.select_id(None);self.dirty=False;self.changed(dirty=False)
    def open_project(self):
        if not self.guard() or not self.confirm_discard():return
        path,_=QFileDialog.getOpenFileName(self,'Mở dự án','','Dự án Huyền Ảnh (*.ha.json)')
        if not path:return
        try:
            data=json.loads(Path(path).read_text(encoding='utf-8'));project=Project.from_dict(data['project'])
            cache_id=data.get('cache_id',uuid.uuid4().hex)
            if not re.fullmatch('[a-f0-9]{32}',cache_id):raise ValueError('ID bộ nhớ voice không hợp lệ.')
            if project.video and not Path(project.video).is_file():
                replacement,_=QFileDialog.getOpenFileName(self,'Video đã di chuyển — chọn lại video nguồn')
                if not replacement:return
                info=probe(replacement)
                if abs(info['duration']-project.duration)>.5:raise ValueError('Thời lượng video mới khác video dự án. Hãy chọn đúng nguồn.')
                project.video=replacement
            self.player.stop();self.editor_dirty=False;self.p=project;self.project_path=Path(path);self.cache_id=cache_id;self.cache=self.cache_root/cache_id;self.cache.mkdir(parents=True,exist_ok=True)
            self.rows={r['id']:r for r in load_manifest(self.cache).get('rows',[])};self.restore_measurements();self.undo=[];self.redo=[];self.clear_region();self.selected=None;self.select_id(None);self.load_controls();self.preview.reset_size();self.load_preview_source();self.dirty=False;self.changed(dirty=False);self.fit_timeline();self.log('Đã mở dự án.')
        except Exception as e:self.error(str(e))
    def save(self,checked=False,save_as=False):
        if not self.guard():return False
        if self.editor_dirty and not self.commit_editor():return False
        path=None if save_as else self.project_path
        if not path:
            suggestion=str(Path(self.p.video).parent/project_filename(self.p.video)) if self.p.video else 'Du-an.ha.json'
            s,_=QFileDialog.getSaveFileName(self,'Lưu dự án theo tên video',suggestion,'Dự án Huyền Ảnh (*.ha.json)')
            if not s:return False
            path=Path(s if s.endswith('.ha.json') else s+'.ha.json')
        try:atomic_json(path,dict(app='HuyenAnhStudio',project=self.p.to_dict(),cache_id=self.cache_id));self.project_path=path;self.dirty=False;self.changed(dirty=False);self.log('Đã lưu dự án: '+str(path));return True
        except Exception as e:self.error(str(e));return False
    def save_srt(self):
        if not self.p.cues:return
        if self.editor_dirty and not self.commit_editor():return
        path,kind=QFileDialog.getSaveFileName(self,'Lưu SRT riêng','Phu-de.srt','Mốc video gốc (*.srt);;Mốc tốc độ dựng (*.srt);;Mốc bản cuối (*.srt)')
        if path:write_srt(path,self.p.cues,self.p.speed if 'bản cuối' in kind else self.p.work_speed if 'dựng' in kind else 1);self.log('Đã lưu SRT: '+path)
    def start_job(self,fn,done,label):
        if not self.guard():return
        self.player.pause();self.voice_player.stop();self.voice_player.setSource(QUrl());self.sample_player.stop();self.busy=True;self.cancel_btn.setEnabled(True);self.progress.setValue(0);self.status.setText(label);self.log(label)
        self.worker=Worker(fn);self.worker.progress.connect(self.job_progress)
        self.pending_result=None;self.pending_error=None
        self.worker.result.connect(lambda result:setattr(self,'pending_result',result));self.worker.failed.connect(lambda error:setattr(self,'pending_error',error))
        completed_worker=self.worker
        def finished():
            self.worker=None
            self.busy=False;self.cancel_btn.setEnabled(False)
            if self.pending_error:self.status.setText('Đã dừng / có lỗi');self.error(self.pending_error)
            else:
                try:done(self.pending_result)
                except Exception as e:self.error(str(e))
            self.refresh_voice_state();completed_worker.deleteLater()
        self.worker.finished.connect(finished);self.worker.start()
    def job_progress(self,n,msg):
        self.progress.setValue(round(n));self.status.setText(msg)
        if getattr(self,'last_msg',None)!=msg:self.log(msg);self.last_msg=msg
    def cancel_job(self):
        if self.worker:self.worker.cancel.set();self.status.setText('Đang hủy tác vụ…')
    def audit_voice_dialog(self,checked=False,only_ids=None):
        if not self.guard():return
        if self.editor_dirty and not self.commit_editor():return
        self.player.pause();self.voice_player.stop();self.sample_player.stop()
        dialog=QDialog(self);dialog.setWindowTitle('Rà soát voice · '+('Phần vừa chạy' if only_ids is not None else 'Toàn dự án'));dialog.resize(1000,570)
        layout=QVBoxLayout(dialog);label=QLabel();label.setWordWrap(True);layout.addWidget(label)
        note=QLabel('Ctrl / Shift để chọn nhiều câu. Câu chỉ có dấu/ký hiệu là gợi ý kiểm tra, không tự xóa.\nKiểm tra file và lỗi đã ghi nhận; chưa đánh giá chất lượng âm thanh hoặc câu tràn mốc.');note.setWordWrap(True);layout.addWidget(note)
        table=QTableWidget(0,5);table.setObjectName('voiceAuditTable');table.setHorizontalHeaderLabels(['Bắt đầu','Kết thúc','Nội dung','Phân loại','Chi tiết lỗi'])
        table.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch);table.setColumnWidth(3,155);table.setColumnWidth(4,230)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.ExtendedSelection);layout.addWidget(table,1)
        display=[];buttons={}
        def selected_ids():return [display[i.row()]['id'] for i in sorted(table.selectionModel().selectedRows(),key=lambda i:i.row())]
        def update_actions():
            n=len(selected_ids())
            for key in ('retry','delete','goto'):buttons[key].setEnabled(n>0)
            buttons['edit'].setEnabled(n==1)
        def refresh():
            result=audit_missing_voice(self.p,self.cache,only_ids);table.clearSelection();display[:]=result['missing'];table.setRowCount(len(display))
            label.setText(f"{result['spoken']} câu có nội dung · {result['available']} câu có MP3 phù hợp · {len(display)} câu thiếu/lỗi")
            names={'symbols':'Chỉ dấu / ký hiệu','error':'Lỗi đã ghi nhận','missing':'Chưa có voice'}
            for i,row in enumerate(display):
                for j,value in enumerate((stamp(row['start']),stamp(row['end']),row['text'],names[row['category']],row['reason'])):
                    item=QTableWidgetItem(value);item.setToolTip(value);table.setItem(i,j,item)
            update_actions()
        def jump():
            ids=selected_ids()
            if ids:dialog.accept();self.navigate_cue(ids[0])
        def retry(all_missing=False):
            ids=[r['id'] for r in display] if all_missing else selected_ids()
            if ids:dialog.accept();self.generate(only_ids=ids)
        def edit():
            ids=selected_ids()
            if len(ids)!=1:return
            cue=next((c for c in self.p.cues if c.id==ids[0]),None)
            if cue is None:return
            text,ok=QInputDialog.getMultiLineText(dialog,'Sửa nội dung câu','Nội dung phụ đề / voice:',cue.text)
            if ok and text!=cue.text:
                self.push_undo();cue.text=text;self.rows.pop(cue.id,None);self.editor_dirty=False;self.changed()
                if self.selected==cue.id:self.select_id(cue.id)
                refresh()
        def delete():
            ids=set(selected_ids())
            if not ids:return
            if QMessageBox.question(dialog,'Xóa câu đã chọn',f'Xóa {len(ids)} câu khỏi phụ đề và timeline?\nCó thể Ctrl+Z sau khi đóng bảng để hoàn tác. File SRT nguồn được giữ nguyên.')!=QMessageBox.Yes:return
            self.push_undo();self.editor_dirty=False;self.p.cues=[c for c in self.p.cues if c.id not in ids]
            for id in ids:self.rows.pop(id,None)
            self.timeline.choose([id for id in self.timeline.selected_ids if id not in ids])
            if self.selected in ids:self.select_id(None)
            self.changed();refresh()
        def select_symbols():
            table.clearSelection()
            from PySide6.QtCore import QItemSelectionModel
            for i,row in enumerate(display):
                if row['category']=='symbols':table.selectionModel().select(table.model().index(i,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
        actions=QHBoxLayout()
        for text,fn in [('Chọn tất cả',table.selectAll),('Chọn câu chỉ có dấu / ký hiệu',select_symbols),('Bỏ chọn',table.clearSelection)]:actions.addWidget(self.button(text,fn))
        layout.addLayout(actions);actions=QHBoxLayout()
        for key,text,fn in [('goto','Tới timeline',jump),('edit','Sửa nội dung…',edit),('delete','Xóa câu đã chọn',delete),('retry','Thử lại câu đã chọn',retry)]:
            buttons[key]=self.button(text,fn,key=='retry');buttons[key].setObjectName('audit_'+key);actions.addWidget(buttons[key])
        layout.addLayout(actions);actions=QHBoxLayout();actions.addWidget(self.button('Thử lại tất cả câu trong bảng',lambda:retry(True)));actions.addWidget(self.button('Đóng',dialog.accept));layout.addLayout(actions)
        table.itemSelectionChanged.connect(update_actions);refresh();dialog.exec();dialog.deleteLater()

    def restore_measurements(self):
        try:metadata=json.loads((self.cache/'audio-metadata.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):return
        for cue in self.p.cues:
            raw=self.cache/(raw_key(cue,self.p)+'.mp3');item=metadata.get(raw.name,{})
            try:
                stat=raw.stat()
                if stat.st_size>0 and item.get('size')==stat.st_size and item.get('mtime')==stat.st_mtime_ns and item.get('duration',0)>0:
                    self.rows[cue.id]=dict(id=cue.id,raw=str(raw),duration=item['duration'])
            except OSError:continue
    def overflow_dialog(self):
        if not self.guard():return
        if self.editor_dirty and not self.commit_editor():return
        self.restore_measurements()
        if not self.rows:
            self.error('Hãy tạo hoặc ghép voice trước để app đo thời lượng câu.');return
        self.player.pause()
        dialog=QDialog(self);dialog.setWindowTitle('Xử lý câu tràn mốc hàng loạt');dialog.resize(920,570)
        layout=QVBoxLayout(dialog)
        note=QLabel('Nới mốc cuối vào khoảng trống trước câu nói tiếp theo. Giữ nguyên lời và mốc bắt đầu.\nKhông gọi lại Edge TTS. Xem đề xuất trước khi áp dụng; Ctrl+Z hoàn tác cả lượt.');note.setWordWrap(True);layout.addWidget(note)
        controls=QFormLayout();scope=QComboBox();scope.addItems(['Toàn dự án','Chỉ vùng đang chọn']);scope.setCurrentIndex(1 if self.selection else 0)
        target=QDoubleSpinBox();target.setRange(1,3);target.setDecimals(2);target.setValue(min(1.25,self.p.max_fit))
        extra=QDoubleSpinBox();extra.setRange(0,10);extra.setDecimals(2);extra.setValue(2);extra.setSuffix(' s')
        gap=QDoubleSpinBox();gap.setRange(0,1);gap.setDecimals(3);gap.setValue(.08);gap.setSuffix(' s')
        controls.addRow('Phạm vi',scope);controls.addRow('Tốc độ ép mong muốn ×',target);controls.addRow('Nới tối đa mỗi câu (giây gốc)',extra);controls.addRow('Chừa khoảng trước câu sau',gap);layout.addLayout(controls)
        summary=QLabel('Bấm Phân tích để xem số câu có thể xử lý.');summary.setWordWrap(True);layout.addWidget(summary)
        table=QTableWidget(0,5);table.setHorizontalHeaderLabels(['Nội dung','Kết thúc cũ','Kết thúc mới','Ép sau nới','Kết quả']);table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch);table.setEditTriggers(QAbstractItemView.NoEditTriggers);layout.addWidget(table,1)
        plan=[None];display_rows=[];apply_button=self.button('Áp dụng mốc',lambda:apply(),True);apply_button.setEnabled(False)
        def analyze():
            try:
                ids=self.region_ids() if scope.currentIndex()==1 else None
                result=plan_overflow(self.p,list(self.rows.values()),ids,target.value(),extra.value(),gap.value());plan[0]=result
                proposed={r['id']:r for r in result['changes']};display_rows.clear()
                for c in self.p.cues:
                    if ids is not None and c.id not in ids:continue
                    if self.row_status(c)[0]!='long':continue
                    measured=self.rows.get(c.id)
                    if not measured:continue
                    factor=max(1,measured['duration']/((c.end-c.start)/self.p.work_speed))
                    display_rows.append(proposed.get(c.id,dict(id=c.id,text=c.text,old_end=c.end,new_end=c.end,after=factor,resolved=False)))
                table.setRowCount(len(display_rows))
                for i,row in enumerate(display_rows):
                    values=[row['text'].replace('\n',' '),stamp(row['old_end']),stamp(row['new_end']),f'{row["after"]:.2f}×','Hết tràn' if row['resolved'] else 'Vẫn cần sửa']
                    for j,value in enumerate(values):table.setItem(i,j,QTableWidgetItem(value))
                summary.setText(f'{result["long_count"]} câu đang tràn → xử lý được {result["solved"]}; còn {result["remaining"]} câu. Nới {len(result["changes"])} mốc. {result["missing"]} câu chưa có số đo phù hợp.')
                apply_button.setEnabled(bool(result['changes']))
            except Exception as e:summary.setText(str(e));apply_button.setEnabled(False)
        def jump(row,column):
            if 0<=row<len(display_rows):
                id=display_rows[row]['id'];dialog.accept();self.navigate_cue(id)
        table.cellClicked.connect(jump)
        def invalidate(*args):plan[0]=None;apply_button.setEnabled(False);summary.setText('Thiết lập đã đổi. Bấm Phân tích lại trước khi áp dụng.')
        scope.currentIndexChanged.connect(invalidate)
        for spin in [target,extra,gap]:spin.valueChanged.connect(invalidate)
        def apply():
            result=plan[0]
            if not result:return
            self.push_undo();updates={r['id']:r['new_end'] for r in result['changes']}
            for cue in self.p.cues:
                if cue.id in updates:cue.end=updates[cue.id]
            self.changed();self.select_id(self.selected);dialog.accept()
            self.log(f'Đã nới {len(updates)} mốc. Dự kiến còn {result["remaining"]} câu tràn. Ctrl+Z để hoàn tác cả lượt.')
            self.status.setText('Đã áp dụng mốc. Khi nghe lô, app sẽ ghép lại voice của lô; MP3 được dùng lại.')
        buttons=QHBoxLayout();buttons.addWidget(self.button('Phân tích',analyze));buttons.addWidget(apply_button);buttons.addWidget(self.button('Đóng',dialog.reject));layout.addLayout(buttons)
        # Modal scope prevents project edits after analysis and before applying the plan.
        analyze();dialog.exec()

    def show_batches(self,checked=False):
        if not self.guard():return
        if self.editor_dirty and not self.commit_editor():return
        if not self.p.video or not self.p.cues:self.error('Mở video và SRT trước.');return
        dialog=QDialog(self);dialog.setWindowTitle('Voice · Chọn lượt cần chạy');dialog.resize(820,620)
        layout=QVBoxLayout(dialog)
        note=QLabel('Chia lượt chỉ để tạo voice, không đổi vị trí phát video.\nChọn 1, vài hoặc tất cả lượt. Câu đã có được dùng lại; lỗi sẽ nghỉ rồi thử lại tối đa 3 lần.');note.setWordWrap(True);layout.addWidget(note)
        row=QHBoxLayout();row.addWidget(QLabel('Mỗi lượt'));minutes=QSpinBox();minutes.setRange(1,120);minutes.setSuffix(' phút');minutes.setValue(self.p.voice_batch_minutes);row.addWidget(minutes)
        for n in (10,20,30):row.addWidget(self.button(f'{n} phút',lambda checked=False,n=n:minutes.setValue(n)))
        layout.addLayout(row);table=QTableWidget(0,4);table.setHorizontalHeaderLabels(['Chạy','Từ','Đến','Voice đã có']);table.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch);table.setEditTriggers(QAbstractItemView.NoEditTriggers);layout.addWidget(table,1)
        batches=[]
        def refill():
            batches.clear();size=minutes.value()*60
            for a in range(0,math.ceil(self.p.duration),size):batches.append((a,min(self.p.duration,a+size)))
            table.setRowCount(len(batches))
            for i,(a,b) in enumerate(batches):
                cues=[c for c in self.p.cues if a<=c.start<b and plain(c.text)]
                ready=sum((self.cache/(raw_key(c,self.p)+'.mp3')).is_file() and (self.cache/(raw_key(c,self.p)+'.mp3')).stat().st_size>0 for c in cues)
                check=QTableWidgetItem();check.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable);check.setCheckState(Qt.Checked if ready<len(cues) else Qt.Unchecked);table.setItem(i,0,check)
                for j,text in enumerate((stamp(a),stamp(b),f'{ready}/{len(cues)}'),1):table.setItem(i,j,QTableWidgetItem(text))
        minutes.valueChanged.connect(refill);refill()
        pick=QHBoxLayout()
        def all_rows(state):
            for i in range(table.rowCount()):table.item(i,0).setCheckState(state)
        pick.addWidget(self.button('Chọn tất cả',lambda:all_rows(Qt.Checked)));pick.addWidget(self.button('Bỏ chọn',lambda:all_rows(Qt.Unchecked)))
        first=QSpinBox();first.setRange(1,max(1,math.ceil(self.p.duration/60)));first.setValue(1);pick.addWidget(first)
        def first_rows():
            for i in range(table.rowCount()):table.item(i,0).setCheckState(Qt.Checked if i<first.value() else Qt.Unchecked)
        pick.addWidget(self.button('Chọn N lượt đầu',first_rows));layout.addLayout(pick)
        parallel=QCheckBox('Chạy song song các lượt đã chọn');parallel.setChecked(True);layout.addWidget(parallel)
        pool=QHBoxLayout();pool.addWidget(QLabel('Giới hạn câu đồng thời (theo chế độ bên dưới)'));workers=QSpinBox();workers.setRange(1,6);workers.setValue(self.p.tts_workers);pool.addWidget(workers);layout.addLayout(pool)
        allocation=QComboBox();allocation.addItems(['Dùng chung giới hạn cho tất cả lô','Giới hạn riêng cho mỗi lô']);layout.addWidget(allocation)
        hint=QLabel();hint.setWordWrap(True);layout.addWidget(hint)
        def explain():
            n=sum(table.item(i,0) is not None and table.item(i,0).checkState()==Qt.Checked for i in range(table.rowCount()));k=workers.value();allocation.setEnabled(parallel.isChecked())
            if not parallel.isChecked():text=f'Tuần tự: tối đa {k} câu của lô 1, xong mới tới lô 2. Không có hai lô chạy cùng lúc.'
            elif allocation.currentIndex()==0:text=f'Dùng chung: tối đa {k} câu cho tổng {n} lô. Xếp xen kẽ các lô; không nhân thành {n*k} câu.'
            else:text=f'Riêng từng lô: tối đa {k} câu/lô × {n} lô = {n*k} câu; giới hạn tổng thực tế {min(24,n*k)} câu (trần 24).'
            hint.setText(text+'\nMột câu xong → nhận câu tiếp theo ngay, không đợi hết nhóm. Khi lỗi mạng, các yêu cầu mới cùng chờ rồi thử lại.')
        parallel.toggled.connect(explain);allocation.currentIndexChanged.connect(explain);workers.valueChanged.connect(explain);table.itemChanged.connect(explain);explain()
        stop=QCheckBox('Chế độ tuần tự: dừng sau lượt còn lỗi');stop.setChecked(True);stop.setEnabled(False);parallel.toggled.connect(lambda on:stop.setEnabled(not on));layout.addWidget(stop)
        def start():
            selected=[b for i,b in enumerate(batches) if table.item(i,0).checkState()==Qt.Checked]
            if not selected:note.setText('Hãy tích ít nhất một lượt cần chạy.');return
            self.p.voice_batch_minutes=minutes.value();self.dirty=True
            self.p.tts_workers=workers.value();self.syncing=True;self.workers.setValue(workers.value());self.syncing=False
            stop_on_error=stop.isChecked();parallel_run=parallel.isChecked();per_batch=parallel_run and allocation.currentIndex()==1;dialog.accept()
            self.run_voice_queue(selected,stop_on_error,parallel=parallel_run,per_batch=per_batch)
        actions=QHBoxLayout();actions.addWidget(self.button('Chạy các lượt đã chọn',start,True));actions.addWidget(self.button('Đóng',dialog.reject));layout.addLayout(actions)
        dialog.exec();dialog.deleteLater()

    def run_voice_queue(self,segments,stop_on_error=True,parallel=False,per_batch=False):
        if not self.guard() or not self.save():return
        try:check_project(self.p)
        except Exception as e:self.error(str(e));return
        p=copy.deepcopy(self.p);cache=self.cache
        def work(cancel,report):
            if parallel:
                ids=interleaved_voice_ids(p,segments)
                if not ids:return dict(rows=[],tts_errors=[],generated_only=True,missing_count=0,queue_completed=len(segments),queue_total=len(segments))
                result=generate_voices(p,cache,cancel,lambda n,msg:report(n,f'Song song {len(segments)} lượt · '+msg),only_ids=ids,mix=False,parallel_segments=segments if per_batch else None)
                result.update(queue_completed=len(segments),queue_total=len(segments));return result
            rows={};errors=[];completed=0;attempted=[]
            for i,(a,b) in enumerate(segments):
                if cancel.is_set():raise InterruptedError('Đã hủy; các câu đã tạo vẫn được giữ.')
                ids=[c.id for c in p.cues if a<=c.start<b and plain(c.text)]
                if ids:
                    result=generate_voices(p,cache,cancel,lambda n,msg:report((i*100+n)/len(segments),f'Lượt {i+1}/{len(segments)} · '+msg),only_ids=ids,mix=False)
                    attempted.extend(ids);rows.update({r['id']:r for r in result['rows']});errors.extend(result.get('tts_errors',[]))
                    completed+=1
                    if stop_on_error and result.get('missing_count'):break
                else:completed+=1
                if i+1<len(segments) and cancel.wait(2):raise InterruptedError('Đã hủy giữa các lượt; voice được giữ.')
            return dict(rows=list(rows.values()),tts_errors=errors,generated_only=True,attempted_ids=attempted,queue_completed=completed,queue_total=len(segments),missing_count=len(errors))
        self.start_job(work,self.voices_done,('Tạo voice song song giữa các lượt' if parallel else 'Tạo voice tuần tự theo lượt')+' · giữ nguyên con trỏ video')

    def generate_selected(self):
        ids=list(self.timeline.selected_ids)
        if not ids:self.status.setText('Chọn câu trên timeline trước; Ctrl+bấm để chọn nhiều câu.');return
        self.generate(only_ids=ids)

    def generate(self,checked=False,only_ids=None,after=None):
        if not self.guard():return
        if not self.save():return
        try:check_project(self.p)
        except Exception as e:self.error(str(e));return
        p=copy.deepcopy(self.p)
        def done(result):
            self.voices_done(result)
            if after:after()
        self.start_job(lambda c,r:generate_voices(p,self.cache,c,r,only_ids=only_ids,mix=False),done,
            'Tạo voice vùng chọn' if only_ids is not None else 'Tạo / cập nhật toàn bộ voice')

    def voices_done(self,result):
        if result.get('generated_only') or result.get('segment') is not None:self.rows.update({r['id']:r for r in result.get('rows',[])})
        else:self.rows={r['id']:r for r in result.get('rows',[])}
        self.refresh_voice_state();self.model.refresh();self.timeline.update()
        bad=result.get('long_count',0);missing=result.get('missing_count',0)
        self.status.setText(f'Đã ghép để nghe · {len(self.rows)} câu có voice · {bad} câu tràn mốc · {missing} câu thiếu')
        if result.get('generated_only'):
            self.status.setText(f'Đã tạo / dùng lại {len(result.get("rows",[]))} câu · {missing} câu lỗi/thiếu. Phát video để nghe tại con trỏ.')
            if 'queue_completed' in result:self.status.setText(f'Đã chạy {result["queue_completed"]}/{result["queue_total"]} lượt · {missing} câu lỗi. Con trỏ video được giữ nguyên.')
        self.progress.setValue(100)
        self.log('Câu màu cam giữ đủ lời, có thể chồng sang câu sau. Câu xám chưa có voice. Có thể sửa từng vùng rồi ghép lại.')
        if result.get('tts_errors'):self.log(f'{len(result["tts_errors"])} câu lỗi; mở Rà thiếu / thử lại câu lỗi trong khu Voice. Các câu thành công được giữ.')
        if result.get('generated_only') and result.get('attempted_ids'):
            ids=list(result['attempted_ids']);project=self.p;cache=self.cache
            def show_errors():
                if self.p is project and self.cache==cache and not self.busy and audit_missing_voice(self.p,cache,ids)['missing']:
                    self.audit_voice_dialog(only_ids=ids)
            QTimer.singleShot(0,show_errors)


    def sample(self):
        if not self.apply_cue():return
        p=copy.deepcopy(self.p);id=self.selected
        def done(result):
            row=result['sample'];self.rows[id]=row;self.model.refresh();self.timeline.update()
            src=row['path'];self.sample_player.setSource(QUrl.fromLocalFile(src));self.sample_player.setPlaybackRate(self.p.final_speed if self.preview_mode.currentIndex()==1 else 1);self.sample_player.play();self.status.setText(f'Nghe câu đã khớp ({row["factor"]:.2f}×)' if row['ok'] else f'Câu quá dài ({row["factor"]:.2f}×) — nghe đủ lời ở tốc độ giới hạn')
        self.start_job(lambda c,r:generate_voices(p,self.cache,c,r,id),done,'Tạo giọng câu đang chọn')
    def export(self,checked=False,voice_choice=None):
        if not self.guard():return
        if not self.save():return
        mode=voice_choice if voice_choice is not None else QMessageBox.question(self,'Xuất video','Xuất kèm voice tiếng Việt?\nCó: video + sub cứng + voice.\nKhông: video + sub cứng + âm gốc theo mức đã chọn.',QMessageBox.Yes|QMessageBox.No|QMessageBox.Cancel)
        if mode==QMessageBox.Cancel:return
        voice=mode==QMessageBox.Yes
        try:
            check_project(self.p)
            if voice and not voice_ready(self.p,self.cache):
                if cached_voice_exists(self.p,self.cache):self.rebuild_existing(after=lambda:self.export(voice_choice=mode));return
                raise ValueError('Chưa có voice. Chọn vùng và tạo voice trước.')
        except Exception as e:self.error(str(e));return
        if voice and not voice_complete(self.p,self.cache):
            m=load_manifest(self.cache)
            message=f'Bản voice hiện có: {len(m.get("rows",[]))} câu; {m.get("missing_count",0)} câu thiếu; {m.get("long_count",0)} câu tràn mốc.\nCâu dài có thể chồng lời; lời vượt hết video sẽ bị giới hạn theo độ dài video.\nXuất bản đang có để xem / chỉnh tiếp?'
            if QMessageBox.question(self,'Xuất bản voice đang có',message)!=QMessageBox.Yes:return
        path,_=QFileDialog.getSaveFileName(self,'Xuất video MP4','Video-Viet.mp4','Video MP4 (*.mp4)',options=QFileDialog.DontConfirmOverwrite)
        if not path:return
        if not path.lower().endswith('.mp4'):path+='.mp4'
        p=copy.deepcopy(self.p);self.start_job(lambda c,r:export_video(p,self.cache,path,c,r,voice,allow_partial=True),self.export_done,'Xuất video hoàn chỉnh')
    def render_sample(self):
        if not self.guard():return
        if self.editor_dirty and not self.commit_editor():return
        try:check_project(self.p)
        except Exception as e:self.error(str(e));return
        p=copy.deepcopy(self.p);cache=self.cache;path=cache/('Xem-thu-'+uuid.uuid4().hex[:6]+'.mp4')
        start=min(max(0,self.source_position()/1000),max(0,p.duration-.1))
        region=self.selection or (start,min(p.duration,start+10*p.speed))
        def work(cancel,report):
            m=rebuild_voice_track(p,cache,cancel,lambda n,msg:report(n*.3,msg),segment=region,include_overlap=True)
            return export_video(p,cache,path,cancel,lambda n,msg:report(30+n*.7,msg),True,allow_partial=True,segment=region,review_voice=m)
        self.start_job(work,self.export_done,'Xuất vùng chọn · chỉ ghép voice trong vùng')

    def export_done(self,path):
        self.status.setText('Đã xuất: '+Path(path).name);self.progress.setValue(100);self.log('Đã xuất: '+path)
        if QMessageBox.question(self,'Xuất hoàn tất',f'Đã lưu:\n{path}\n\nMở video để xem?')==QMessageBox.Yes:QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    def save_voice(self):
        if not self.guard():return
        if self.editor_dirty and not self.commit_editor():return
        if self._batch_segment is not None:
            m=batch_manifest(self.p,self.cache,self._batch_segment)
            if not m:self.error('Voice của lô cần cập nhật. Mở Voice theo đợt để ghép lại phần đang có.');return
            a,b=self._batch_segment
            name=project_filename(self.p.video).removesuffix('.ha.json')+'-voice-'+stamp(a).replace(':','-')+'_'+stamp(b).replace(':','-')+'.wav'
            source=Path(m['track']);title='Lưu voice riêng của lô theo tốc độ dựng'
        else:
            if not voice_ready(self.p,self.cache):
                if cached_voice_exists(self.p,self.cache):self.rebuild_existing(after=self.save_voice);return
                self.error('Chưa có voice để lưu.');return
            source=voice_track_path(self.cache);name='Voice-Viet.wav';title='Lưu voice toàn phim theo tốc độ dựng'
        path,_=QFileDialog.getSaveFileName(self,title,name,'Wave (*.wav)')
        if path:
            if Path(path).resolve()!=source.resolve():shutil.copy2(source,path)
            self.log('Đã lưu voice WAV theo tốc độ dựng: '+path)
    def closeEvent(self,event):
        if self.busy:self.error('Hãy hủy hoặc đợi tác vụ hoàn tất trước khi đóng.');event.ignore();return
        if not self.confirm_discard():event.ignore();return
        self.close_cpu();self.player.stop();self.voice_player.stop();self.sample_player.stop();event.accept()

def voice_ready_cached(win):return getattr(win,'voice_is_ready',False)

THEME='''
QWidget { background: #121820; color: #dce6ee; font-family: "Segoe UI", "Arial"; font-size: 12px; }
QMainWindow {background:#0c1118;} QLabel#brand {font-size:18px;font-weight:700;letter-spacing:2px;color:#7ce0cd;}
QLabel#muted {color:#8fa0b1;font-size:11px;} QPushButton {background:#263241;border:1px solid #344354;border-radius:6px;padding:8px 11px;}
QPushButton:hover {background:#344556;border-color:#6ea99f;} QPushButton:pressed {background:#1d665e;}
QPushButton#primary {background:#76ddc7;color:#082d28;border:none;font-weight:700;} QPushButton#primary:hover {background:#a3f1e0;}
QPushButton:disabled {color:#6a7684;background:#1a232e;} QLineEdit,QTextEdit,QPlainTextEdit,QComboBox,QDoubleSpinBox,QSpinBox {background:#0d141d;border:1px solid #334354;border-radius:4px;padding:5px;selection-background-color:#216e65;}
QTableView {background:#111923;alternate-background-color:#18212b;border:1px solid #293744;gridline-color:#202e3d;selection-background-color:#28544f;selection-color:#ffffff;}
QHeaderView::section {background:#1f2b38;border:0;padding:7px;color:#a0b2c4;} QGroupBox {border:1px solid #2d3a49;border-radius:6px;margin-top:17px;padding:12px 7px 7px;}
QGroupBox::title {subcontrol-origin:margin;left:10px;color:#a8c0ce;padding:0 4px;} QScrollArea {border:0;}
QSlider::groove:horizontal {height:5px;background:#2b3b4b;border-radius:2px;} QSlider::handle:horizontal {width:13px;margin:-5px 0;background:#7fe1ce;border-radius:6px;}
QProgressBar {border:1px solid #304253;border-radius:5px;background:#101720;text-align:center;height:20px;} QProgressBar::chunk {background:#277b70;border-radius:4px;}
QScrollBar:vertical {background:#131c26;width:10px;} QScrollBar::handle:vertical {background:#3b4e61;min-height:24px;border-radius:4px;}
QScrollBar:horizontal {background:#15202b;height:12px;} QScrollBar::handle:horizontal {background:#405467;min-width:25px;border-radius:4px;}
QSplitter::handle {background:#263440;width:3px;} QToolTip {background:#243240;color:white;border:1px solid #596f82;}
'''

def main():
    app=QApplication(sys.argv);app.setApplicationName('HuyenAnhStudio');app.setOrganizationName('HuyenAnh');app.setStyle('Fusion');app.setStyleSheet(THEME)
    win=Window();win.show();sys.exit(app.exec())
