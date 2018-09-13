# pylint: disable=W0221,E1101
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable
from models.layers.VerboseGradients import VerboseGradients
from models.layers.BalanceLabels import BalanceLabels
from models.layers.utils import gtmat, winsmooth


def _expand(arr, factor):
    return [x for x in arr for _ in range(factor)]


class DefaultCriterion(nn.Module):
    def __init__(self, args):
        nn.Module.__init__(self)
        self.orig_loss = args.originalloss_weight
        self.adjustment = args.adjustment
        self.loss = nn.BCELoss()
        self.balanceloss = args.balanceloss
        self.BalanceLabels = BalanceLabels()
        self.winsmooth = args.window_smooth
        self.videoloss = args.videoloss

    def forward(self, a, target, id_time, synchronous=False):
        idtime = zip(id_time['id'], id_time['time'])
        nc = a.shape[1]
        if a.dim() == 3:
            # temporal mode
            if self.training:
                # max over time, and add it to the batch
                a_video = a.mean(dim=2)
                a = F.upsample(a, target.shape[1], mode='linear', align_corners=True)
                target_video = target.max(dim=1)[0]
                idtime_video = idtime

                # unroll over time
                a = a.permute(0, 2, 1).contiguous().view(-1, nc)
                target = target.permute(0, 1, 2).contiguous().view(-1, nc)
                idtime = _expand(idtime, a.shape[0] / len(idtime))

                # combine both
                a = torch.cat([a, a_video])
                target = torch.cat([target, target_video])
                idtime = idtime + idtime_video
            else:
                a = a.mean(dim=2)
                target = target.max(dim=1)[0]

        if target.dim() == 1:
            print('converting Nx1 target to NxC')
            target = Variable(gtmat(a.shape, target.data.long()))
        target = target.float()

        a, = VerboseGradients.apply(a)
        if self.balanceloss and self.training:
            print('balancing loss')
            a = self.BalanceLabels(a, target)

        loss = self.loss(torch.nn.Sigmoid()(a), target) * self.orig_loss
        if self.videoloss:
            assert synchronous, 'videoloss only makes sense if there is only one video per batch'
            print('applying video loss')
            loss += self.loss(torch.max(torch.nn.Sigmoid()(a), dim=0)[0], torch.max(target, dim=0)[0]) * self.orig_loss
        print('losses class: {}'.format(loss.data[0]))

        if synchronous:
            a = winsmooth(a, kernelsize=self.winsmooth)
        return a, loss, target
