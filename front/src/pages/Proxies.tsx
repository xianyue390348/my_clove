import { useEffect, useState } from 'react'
import { Plus, Trash2, Server, AlertCircle, Info } from 'lucide-react'
import type { ProxyResponse } from '../api/types'
import { proxiesApi } from '../api/client'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { toast } from 'sonner'
import { useIsMobile } from '@/hooks/use-mobile'

export function Proxies() {
    const [proxies, setProxies] = useState<ProxyResponse[]>([])
    const [loading, setLoading] = useState(true)
    const [addDialogOpen, setAddDialogOpen] = useState(false)
    const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
    const [proxyToDelete, setProxyToDelete] = useState<ProxyResponse | null>(null)
    const [newProxyUrl, setNewProxyUrl] = useState('')
    const [addingProxy, setAddingProxy] = useState(false)
    const isMobile = useIsMobile()

    const loadProxies = async () => {
        try {
            const response = await proxiesApi.list()
            setProxies(response.data)
        } catch (error) {
            console.error('Failed to load proxies:', error)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        loadProxies()
    }, [])

    const handleDelete = async () => {
        if (!proxyToDelete) return

        try {
            await proxiesApi.delete(proxyToDelete.index)
            toast.success('代理删除成功')
            await loadProxies()
            setDeleteDialogOpen(false)
            setProxyToDelete(null)
        } catch (error) {
            console.error('Failed to delete proxy:', error)
        }
    }

    const handleAdd = async () => {
        if (!newProxyUrl.trim()) {
            toast.error('请输入代理URL')
            return
        }

        // 验证格式
        const proxyPattern = /^socks5:\/\/[\w.-]+(?::[\w.-]+)?@[\w.-]+:\d+$/
        if (!proxyPattern.test(newProxyUrl.trim())) {
            toast.error('代理URL格式不正确，应为: socks5://user:pass@host:port')
            return
        }

        setAddingProxy(true)
        try {
            await proxiesApi.create({ url: newProxyUrl.trim() })
            toast.success('代理添加成功')
            await loadProxies()
            setAddDialogOpen(false)
            setNewProxyUrl('')
        } catch (error) {
            console.error('Failed to add proxy:', error)
        } finally {
            setAddingProxy(false)
        }
    }

    const openDeleteDialog = (proxy: ProxyResponse) => {
        setProxyToDelete(proxy)
        setDeleteDialogOpen(true)
    }

    const openAddDialog = () => {
        setNewProxyUrl('')
        setAddDialogOpen(true)
    }

    if (loading) {
        return (
            <div className="container mx-auto p-4 space-y-4">
                <div className="flex items-center justify-between">
                    <Skeleton className="h-8 w-32" />
                    <Skeleton className="h-10 w-24" />
                </div>
                <Skeleton className="h-[400px] w-full" />
            </div>
        )
    }

    return (
        <div className="container mx-auto p-4 space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold">代理池管理</h1>
                    <p className="text-muted-foreground mt-1">管理 SOCKS5 代理，账户将自动分配代理</p>
                </div>
                <Button onClick={openAddDialog}>
                    <Plus className="mr-2 h-4 w-4" />
                    添加代理
                </Button>
            </div>

            <Alert>
                <Info className="h-4 w-4" />
                <AlertDescription>
                    账户将根据索引自动分配代理（取模算法）。例如：8个账户、3个代理时，账户0/3/6使用代理0，账户1/4/7使用代理1，账户2/5使用代理2。
                </AlertDescription>
            </Alert>

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center">
                        <Server className="mr-2 h-5 w-5" />
                        代理列表
                    </CardTitle>
                    <CardDescription>
                        当前共有 {proxies.length} 个代理
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {proxies.length === 0 ? (
                        <div className="text-center py-12">
                            <AlertCircle className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                            <p className="text-muted-foreground">暂无代理</p>
                            <p className="text-sm text-muted-foreground mt-1">
                                点击"添加代理"按钮开始添加
                            </p>
                        </div>
                    ) : (
                        <div className="rounded-md border">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead className="w-20">索引</TableHead>
                                        <TableHead>代理地址</TableHead>
                                        <TableHead className="w-24 text-right">操作</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {proxies.map((proxy) => (
                                        <TableRow key={proxy.index}>
                                            <TableCell className="font-mono">{proxy.index}</TableCell>
                                            <TableCell className="font-mono text-sm">
                                                {proxy.masked_url}
                                            </TableCell>
                                            <TableCell className="text-right">
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => openDeleteDialog(proxy)}
                                                >
                                                    <Trash2 className="h-4 w-4 text-destructive" />
                                                </Button>
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* 添加代理对话框 */}
            <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>添加代理</DialogTitle>
                        <DialogDescription>
                            添加新的 SOCKS5 代理到代理池
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="space-y-2">
                            <Label htmlFor="proxy-url">代理 URL</Label>
                            <Input
                                id="proxy-url"
                                placeholder="socks5://user:pass@host:port"
                                value={newProxyUrl}
                                onChange={(e) => setNewProxyUrl(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' && !addingProxy) {
                                        handleAdd()
                                    }
                                }}
                            />
                            <p className="text-sm text-muted-foreground">
                                格式：socks5://username:password@host:port
                            </p>
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setAddDialogOpen(false)}>
                            取消
                        </Button>
                        <Button onClick={handleAdd} disabled={addingProxy}>
                            {addingProxy ? '添加中...' : '添加'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* 删除确认对话框 */}
            <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>确认删除</AlertDialogTitle>
                        <AlertDialogDescription>
                            确定要删除代理 <span className="font-mono">{proxyToDelete?.masked_url}</span> 吗？
                            删除后，账户将重新分配代理。
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>取消</AlertDialogCancel>
                        <AlertDialogAction onClick={handleDelete}>删除</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    )
}
