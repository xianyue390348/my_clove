import { useState, useEffect } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { conversationLogsApi } from '@/api/client'
import type { ConversationLog } from '@/api/types'
import { toast } from 'sonner'
import { RefreshCw, Search, Trash2, Eye, Clock, CheckCircle2, XCircle, Loader2 } from 'lucide-react'

export function ConversationLogs() {
    const [logs, setLogs] = useState<ConversationLog[]>([])
    const [loading, setLoading] = useState(false)
    const [selectedLog, setSelectedLog] = useState<ConversationLog | null>(null)
    const [detailOpen, setDetailOpen] = useState(false)

    // 筛选条件
    const [filters, setFilters] = useState({
        session_id: '',
        status: 'all' as 'all' | 'success' | 'error',
        start_date: '',
        end_date: '',
    })

    const loadLogs = async () => {
        try {
            setLoading(true)
            const params: any = {
                limit: 100,
            }

            if (filters.session_id) {
                params.session_id = filters.session_id
            }
            if (filters.status !== 'all') {
                params.status = filters.status
            }
            if (filters.start_date) {
                params.start_date = filters.start_date
            }
            if (filters.end_date) {
                params.end_date = filters.end_date
            }

            const response = await conversationLogsApi.list(params)
            setLogs(response.data.logs)
        } catch (error) {
            console.error('Failed to load logs:', error)
        } finally {
            setLoading(false)
        }
    }

    const handleCleanup = async () => {
        if (!confirm('确定要清理过期的日志吗？此操作不可撤销。')) {
            return
        }

        try {
            const response = await conversationLogsApi.cleanup()
            toast.success(`已清理 ${response.data.deleted_files} 个过期日志文件`)
            loadLogs()
        } catch (error) {
            console.error('Failed to cleanup logs:', error)
        }
    }

    const viewDetail = async (log: ConversationLog) => {
        setSelectedLog(log)
        setDetailOpen(true)
    }

    useEffect(() => {
        loadLogs()
    }, [])

    const formatTimestamp = (timestamp: string) => {
        return new Date(timestamp).toLocaleString('zh-CN')
    }

    const formatDuration = (ms: number) => {
        if (ms < 1000) return `${ms}ms`
        return `${(ms / 1000).toFixed(2)}s`
    }

    return (
        <div className='space-y-6'>
            <div>
                <h1 className='text-3xl font-bold'>对话日志</h1>
                <p className='text-muted-foreground mt-2'>查看和分析 API 对话记录</p>
            </div>

            {/* 筛选条件 */}
            <Card className='p-4'>
                <div className='grid grid-cols-1 md:grid-cols-4 gap-4'>
                    <div>
                        <label className='text-sm font-medium mb-2 block'>Session ID</label>
                        <Input
                            placeholder='搜索 Session ID'
                            value={filters.session_id}
                            onChange={e => setFilters({ ...filters, session_id: e.target.value })}
                        />
                    </div>
                    <div>
                        <label className='text-sm font-medium mb-2 block'>状态</label>
                        <Select value={filters.status} onValueChange={value => setFilters({ ...filters, status: value as any })}>
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value='all'>全部</SelectItem>
                                <SelectItem value='success'>成功</SelectItem>
                                <SelectItem value='error'>错误</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <label className='text-sm font-medium mb-2 block'>开始日期</label>
                        <Input
                            type='date'
                            value={filters.start_date}
                            onChange={e => setFilters({ ...filters, start_date: e.target.value })}
                        />
                    </div>
                    <div>
                        <label className='text-sm font-medium mb-2 block'>结束日期</label>
                        <Input
                            type='date'
                            value={filters.end_date}
                            onChange={e => setFilters({ ...filters, end_date: e.target.value })}
                        />
                    </div>
                </div>
                <div className='flex gap-2 mt-4'>
                    <Button onClick={loadLogs} disabled={loading}>
                        {loading ? <Loader2 className='mr-2 h-4 w-4 animate-spin' /> : <Search className='mr-2 h-4 w-4' />}
                        查询
                    </Button>
                    <Button onClick={loadLogs} variant='outline' disabled={loading}>
                        <RefreshCw className='mr-2 h-4 w-4' />
                        刷新
                    </Button>
                    <Button onClick={handleCleanup} variant='destructive' className='ml-auto'>
                        <Trash2 className='mr-2 h-4 w-4' />
                        清理过期日志
                    </Button>
                </div>
            </Card>

            {/* 日志列表 */}
            <Card>
                <div className='p-4 border-b'>
                    <h2 className='text-lg font-semibold'>日志记录 ({logs.length})</h2>
                </div>
                <div className='divide-y'>
                    {logs.length === 0 && !loading && (
                        <div className='p-8 text-center text-muted-foreground'>暂无日志记录</div>
                    )}
                    {logs.map(log => (
                        <div key={log.log_id} className='p-4 hover:bg-muted/50 transition-colors'>
                            <div className='flex items-start justify-between'>
                                <div className='flex-1 space-y-2'>
                                    <div className='flex items-center gap-2'>
                                        {log.status === 'success' ? (
                                            <CheckCircle2 className='h-5 w-5 text-green-500' />
                                        ) : (
                                            <XCircle className='h-5 w-5 text-red-500' />
                                        )}
                                        <Badge variant={log.status === 'success' ? 'default' : 'destructive'}>
                                            {log.status}
                                        </Badge>
                                        {log.is_streaming && <Badge variant='outline'>流式</Badge>}
                                        <span className='text-sm text-muted-foreground flex items-center gap-1'>
                                            <Clock className='h-3 w-3' />
                                            {formatDuration(log.duration_ms)}
                                        </span>
                                    </div>
                                    <div className='grid grid-cols-2 md:grid-cols-4 gap-4 text-sm'>
                                        <div>
                                            <span className='text-muted-foreground'>时间：</span>
                                            <span className='font-mono'>{formatTimestamp(log.timestamp)}</span>
                                        </div>
                                        <div>
                                            <span className='text-muted-foreground'>Session：</span>
                                            <span className='font-mono text-xs'>
                                                {log.session_id?.substring(0, 16)}...
                                            </span>
                                        </div>
                                        {log.account_id && (
                                            <div>
                                                <span className='text-muted-foreground'>账户：</span>
                                                <span className='font-mono text-xs'>
                                                    {log.account_id.substring(0, 8)}...
                                                </span>
                                            </div>
                                        )}
                                        {log.conversation_id && (
                                            <div>
                                                <span className='text-muted-foreground'>对话：</span>
                                                <span className='font-mono text-xs'>
                                                    {log.conversation_id.substring(0, 8)}...
                                                </span>
                                            </div>
                                        )}
                                    </div>
                                    {log.error && (
                                        <div className='text-sm text-red-600 bg-red-50 dark:bg-red-950 p-2 rounded'>
                                            <strong>{log.error.type}:</strong> {log.error.message}
                                        </div>
                                    )}
                                </div>
                                <Button variant='outline' size='sm' onClick={() => viewDetail(log)}>
                                    <Eye className='h-4 w-4 mr-2' />
                                    详情
                                </Button>
                            </div>
                        </div>
                    ))}
                </div>
            </Card>

            {/* 详情弹窗 */}
            <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
                <DialogContent className='max-w-4xl max-h-[80vh] overflow-y-auto'>
                    <DialogHeader>
                        <DialogTitle>对话详情</DialogTitle>
                        <DialogDescription>
                            Log ID: {selectedLog?.log_id}
                        </DialogDescription>
                    </DialogHeader>
                    {selectedLog && (
                        <div className='space-y-4'>
                            {/* 基础信息 */}
                            <div>
                                <h3 className='font-semibold mb-2'>基础信息</h3>
                                <div className='bg-muted p-3 rounded space-y-1 text-sm'>
                                    <div><strong>时间：</strong>{formatTimestamp(selectedLog.timestamp)}</div>
                                    <div><strong>耗时：</strong>{formatDuration(selectedLog.duration_ms)}</div>
                                    <div><strong>状态：</strong>{selectedLog.status}</div>
                                    <div><strong>流式：</strong>{selectedLog.is_streaming ? '是' : '否'}</div>
                                    <div><strong>Session ID：</strong><code className='text-xs'>{selectedLog.session_id}</code></div>
                                    {selectedLog.conversation_id && (
                                        <div><strong>Conversation ID：</strong><code className='text-xs'>{selectedLog.conversation_id}</code></div>
                                    )}
                                    {selectedLog.account_id && (
                                        <div><strong>Account ID：</strong><code className='text-xs'>{selectedLog.account_id}</code></div>
                                    )}
                                </div>
                            </div>

                            {/* 客户端请求 */}
                            {selectedLog.client_request && (
                                <div>
                                    <h3 className='font-semibold mb-2'>客户端请求</h3>
                                    <pre className='bg-muted p-3 rounded text-xs overflow-x-auto'>
                                        {JSON.stringify(selectedLog.client_request, null, 2)}
                                    </pre>
                                </div>
                            )}

                            {/* Claude Web 请求 */}
                            {selectedLog.claude_web_request && (
                                <div>
                                    <h3 className='font-semibold mb-2'>Claude Web 请求</h3>
                                    <pre className='bg-muted p-3 rounded text-xs overflow-x-auto'>
                                        {JSON.stringify(selectedLog.claude_web_request, null, 2)}
                                    </pre>
                                </div>
                            )}

                            {/* 响应消息 */}
                            {selectedLog.collected_message && (
                                <div>
                                    <h3 className='font-semibold mb-2'>响应消息</h3>
                                    <pre className='bg-muted p-3 rounded text-xs overflow-x-auto'>
                                        {JSON.stringify(selectedLog.collected_message, null, 2)}
                                    </pre>
                                </div>
                            )}

                            {/* 错误信息 */}
                            {selectedLog.error && (
                                <div>
                                    <h3 className='font-semibold mb-2 text-red-600'>错误信息</h3>
                                    <div className='bg-red-50 dark:bg-red-950 p-3 rounded'>
                                        <div><strong>类型：</strong>{selectedLog.error.type}</div>
                                        <div><strong>消息：</strong>{selectedLog.error.message}</div>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </DialogContent>
            </Dialog>
        </div>
    )
}
