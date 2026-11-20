//! Executor assíncrono mínimo. Todo o kernel acima das interrupções
//! roda como tarefas `async`; a CPU dorme (hlt) quando não há trabalho.

use alloc::boxed::Box;
use alloc::collections::BTreeMap;
use alloc::sync::Arc;
use alloc::task::Wake;
use core::future::Future;
use core::pin::Pin;
use core::sync::atomic::{AtomicU64, Ordering};
use core::task::{Context, Poll, Waker};
use crossbeam_queue::ArrayQueue;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
struct TaskId(u64);

impl TaskId {
    fn new() -> Self {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        TaskId(NEXT.fetch_add(1, Ordering::Relaxed))
    }
}

pub struct Task {
    id: TaskId,
    future: Pin<Box<dyn Future<Output = ()>>>,
}

impl Task {
    pub fn new(future: impl Future<Output = ()> + 'static) -> Self {
        Task { id: TaskId::new(), future: Box::pin(future) }
    }
}

/// Tarefas criadas de dentro de outras tarefas (ex.: um driver que acha um teclado).
/// Por enquanto o kernel roda num núcleo só, então as tarefas nunca mudam de CPU.
struct SpawnList(alloc::vec::Vec<Task>);
unsafe impl Send for SpawnList {}

static SPAWNED: spin::Mutex<SpawnList> = spin::Mutex::new(SpawnList(alloc::vec::Vec::new()));

pub fn spawn(future: impl Future<Output = ()> + 'static) {
    SPAWNED.lock().0.push(Task::new(future));
}

pub struct Executor {
    tasks: BTreeMap<TaskId, Task>,
    queue: Arc<ArrayQueue<TaskId>>,
    wakers: BTreeMap<TaskId, Waker>,
}

impl Executor {
    pub fn new() -> Self {
        Executor {
            tasks: BTreeMap::new(),
            queue: Arc::new(ArrayQueue::new(128)),
            wakers: BTreeMap::new(),
        }
    }

    pub fn spawn(&mut self, task: Task) {
        let id = task.id;
        self.tasks.insert(id, task);
        self.queue.push(id).expect("fila de tarefas cheia");
    }

    pub fn run(&mut self) -> ! {
        loop {
            self.run_ready();
            self.sleep_if_idle();
        }
    }

    fn run_ready(&mut self) {
        let new: alloc::vec::Vec<Task> = core::mem::take(&mut SPAWNED.lock().0);
        for t in new {
            self.spawn(t);
        }
        while let Some(id) = self.queue.pop() {
            let Some(task) = self.tasks.get_mut(&id) else { continue };
            let waker = self
                .wakers
                .entry(id)
                .or_insert_with(|| Waker::from(Arc::new(TaskWaker { id, queue: self.queue.clone() })));
            let mut cx = Context::from_waker(waker);
            if let Poll::Ready(()) = task.future.as_mut().poll(&mut cx) {
                self.tasks.remove(&id);
                self.wakers.remove(&id);
            }
        }
    }

    fn sleep_if_idle(&self) {
        use x86_64::instructions::interrupts;
        interrupts::disable();
        if self.queue.is_empty() && SPAWNED.lock().0.is_empty() {
            interrupts::enable_and_hlt();
        } else {
            interrupts::enable();
        }
    }
}

struct TaskWaker {
    id: TaskId,
    queue: Arc<ArrayQueue<TaskId>>,
}

impl Wake for TaskWaker {
    fn wake(self: Arc<Self>) {
        let _ = self.queue.push(self.id);
    }
    fn wake_by_ref(self: &Arc<Self>) {
        let _ = self.queue.push(self.id);
    }
}
