#include "../../src/dxmt/dxmt_tasks.hpp"
#include <cassert>
#include <future>
#include <memory>

// Native Win32 compatibility helpers only need this logging entry point.
void dxmt::Logger::warn(const std::string &) {}

struct Task {
  std::promise<void> entered;
  std::shared_future<void> release;
  std::atomic_bool done = false;
  std::atomic_bool &completed;
  std::atomic_bool &destroyed;
  ~Task() { destroyed = true; }
};

template <> struct dxmt::task_trait<Task *> {
  Task *run_task(Task *task) {
    task->entered.set_value();
    task->release.wait();
    assert(!task->destroyed.load());
    task->completed = true;
    return task;
  }
  bool get_done(Task *task) { return task->done; }
  void set_done(Task *task) { task->done = true; }
};

int main() {
  for (int iteration = 0; iteration < 50; ++iteration) {
    std::promise<void> release;
    std::atomic_bool completed = false, destroyed = false;
    // Match PipelineCache: the scheduler precedes its task-owning storage.
    struct Owner {
      dxmt::task_scheduler<Task *> scheduler;
      std::unique_ptr<Task> task;
      ~Owner() { scheduler.shutdown(); }
    };
    auto owner = std::make_unique<Owner>();
    owner->task = std::unique_ptr<Task>(new Task{{}, release.get_future().share(), false, completed, destroyed});
    auto entered = owner->task->entered.get_future();
    owner->scheduler.submit(owner->task.get());
    assert(entered.wait_for(std::chrono::seconds(5)) == std::future_status::ready);
    auto destroying = std::async(std::launch::async, [&] { owner.reset(); });
    assert(destroying.wait_for(std::chrono::milliseconds(10)) == std::future_status::timeout);
    assert(!destroyed);
    release.set_value();
    assert(destroying.wait_for(std::chrono::seconds(5)) == std::future_status::ready);
    destroying.get();
    assert(completed && destroyed);
  }
  // Also cover sleeping workers, repeated shutdown, and late submissions.
  dxmt::task_scheduler<Task *> idle;
  idle.shutdown();
  idle.shutdown();
  idle.submit(nullptr);
}
